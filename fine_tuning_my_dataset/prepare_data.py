#!/usr/bin/env python3
"""Build train/valid/eval JSONL for the 'Mexamen' multiple-choice task from data/questions.json.

Pipeline: build 4-option questions -> normalise formatting -> drop broken / near-duplicate items
-> sample 30 for manual review -> apply manual drops -> group split (near-duplicates never straddle
splits) -> shuffle option order so the correct letter is balanced inside every split.
Writes data/{train,valid,eval}.jsonl, data/review_sample.md, data/report.json.
"""
import argparse
import collections
import json
import random
import re
from pathlib import Path

from common import LETTERS, format_answer, norm, plain_messages

SEED = 42
MAX_OPTION_CHARS = 140

# The 30 items reviewed by hand: a seeded random draw (random.Random(43).sample) from the cleaned pool,
# frozen here because later cleaning rules change the pool and would reshuffle a fresh draw.
REVIEWED_IDS = [40, 322, 153, 524, 426, 757, 104, 515, 678, 564, 688, 20, 582, 492, 655, 429, 705, 619, 494, 453, 188, 61, 115, 133, 432, 163, 171, 579, 561, 137]

# Found while reading the 30-item random sample and the near-duplicate pair list (see README).
MANUAL_DROP = {
    # id: reason
    764: "same question as 765 with conflicting answers (35 vs 27 UNESCO sites)",
    765: "same question as 764 with conflicting answers (35 vs 27 UNESCO sites)",
    # from the 30-item review sample (review_sample.md):
    564: "first credencial de elector: 1990 vs 1992, both present, key is doubtful (sample #10)",
    153: "'fertility goddess': Coatlicue vs Xochiquetzal/Tlazolteotl, debatable key (sample #3)",
    688: "'year the new era of Mexican cinema starts' is a matter of opinion (sample #11)",
    # found by grep while fixing formatting:
    453: "answer written 'Rio' without accent while distractors have 'Río' (shortcut), 4-part answers",
}


def clean_option(s):
    s = s.replace("“", '"').replace("”", '"').replace("«", '"').replace("»", '"').replace("’", "'")
    s = " ".join(s.split())
    stripped = re.sub(r"\s*\([^)]*\)\s*$", "", s)  # trailing '(…)' comment: only the correct answers had it
    s = stripped or s
    s = s.rstrip(" .;,:")
    return s[:1].upper() + s[1:]


def grams(s, n=3):
    s = norm(s)
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def sim(a, b):
    ga, gb = grams(a), grams(b)
    if not ga or not gb:
        return float(norm(a) == norm(b))
    return len(ga & gb) / len(ga | gb)


def build_candidates(rows, stats):
    out = []
    for r in rows:
        ans = clean_option(r["answer"])
        seen = {norm(ans)}
        dist = []
        # real (exam) distractors first; model-made synthetic ones only top up a missing slot
        for pool_name in ("realDistractors", "syntheticDistractors"):
            if len(dist) >= 3:
                break
            for d in r.get(pool_name) or []:
                d = clean_option(d)
                if d and norm(d) not in seen:
                    seen.add(norm(d))
                    dist.append(d)
        if len(dist) < 3:
            stats["dropped_lt3_distractors"] += 1
            continue
        dist = dist[:3]
        if max(len(o) for o in dist + [ans]) > MAX_OPTION_CHARS:
            stats["dropped_long_option"] += 1
            continue
        out.append({"id": r["id"], "section": r["section"], "question": " ".join(r["question"].split()),
                    "answer": ans, "distractors": dist})
    return out


def near_dup_groups(items, stats):
    """Union-find. Edge 'dup': similar question AND similar answer -> keep one. Edge 'related': similar
    question -> same split (so a reworded question can't leak from train into eval)."""
    parent = list(range(len(items)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    drop, related_pairs = set(), []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            qs = sim(items[i]["question"], items[j]["question"])
            if qs < 0.6:
                continue
            as_ = sim(items[i]["answer"], items[j]["answer"])
            if re.findall(r"\d+", items[i]["answer"]) != re.findall(r"\d+", items[j]["answer"]):
                as_ = 0.0  # 'Artículo 5' vs 'Artículo 6': different facts, however similar the strings
            if as_ >= 0.5:
                drop.add(j)  # j has the larger id: keep the earlier one
                stats["dropped_near_dup"] += 1
            related_pairs.append((round(qs, 2), round(as_, 2), items[i]["id"], items[j]["id"]))
            if qs >= 0.75 or as_ >= 0.5:
                parent[find(i)] = find(j)
    return drop, [find(i) for i in range(len(items))], related_pairs


def assign_positions(items, rng):
    """Correct letter exactly balanced; remaining option order random."""
    pos = [i % 4 for i in range(len(items))]
    rng.shuffle(pos)
    out = []
    for it, p in zip(items, pos):
        rest = it["distractors"][:]
        rng.shuffle(rest)
        opts = rest[:p] + [it["answer"]] + rest[p:]
        out.append({"id": it["id"], "section": it["section"], "question": it["question"], "options": opts,
                    "answer_idx": p, "letter": LETTERS[p],
                    "messages": plain_messages(it["question"], opts)
                    + [{"role": "assistant", "content": format_answer(opts, p)}]})
    return out


def shortcut_stats(items):
    n = len(items)
    longest = sum(len(i["answer"]) > max(map(len, i["distractors"])) for i in items)
    return {"n": n,
            "answer_longest": round(longest / n, 3),
            "answer_ends_with_dot": round(sum(i["answer"].endswith(".") for i in items) / n, 3),
            "answer_has_paren": round(sum("(" in i["answer"] for i in items) / n, 3),
            "distractor_has_paren": round(sum("(" in d for i in items for d in i["distractors"]) / (3 * n), 3),
            "answer_starts_lower": round(sum(i["answer"][:1].islower() for i in items) / n, 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="data/questions.json")
    ap.add_argument("--out", default="data")
    ap.add_argument("--n-eval", type=int, default=150)
    ap.add_argument("--n-valid", type=int, default=50)
    args = ap.parse_args()
    out = Path(args.out)
    rng = random.Random(SEED)

    rows = json.load(open(args.src, encoding="utf-8"))
    stats = collections.Counter(raw=len(rows))
    raw_items = [{"id": r["id"], "section": r["section"], "question": r["question"], "answer": r["answer"],
                  "distractors": (r.get("realDistractors") or r.get("syntheticDistractors") or [])[:3]}
                 for r in rows]
    report = {"shortcuts_before_cleaning": shortcut_stats(raw_items)}

    items = build_candidates(rows, stats)
    drop, group, related = near_dup_groups(items, stats)
    pool_auto = [it for i, it in enumerate(items) if i not in drop]
    stats["after_auto_clean"] = len(pool_auto)

    by_id = {it["id"]: it for it in items}
    sample = [by_id[i] for i in REVIEWED_IDS]
    with open(out / "review_sample.md", "w", encoding="utf-8") as f:
        for k, it in enumerate(sample, 1):
            f.write(f"{k}. [id {it['id']}] ({it['section']}) {it['question']}\n   OK: {it['answer']}\n"
                    f"   distractors: {' | '.join(it['distractors'])}\n")

    keep_ids = {it["id"] for it in pool_auto} - set(MANUAL_DROP)
    stats["dropped_manual"] = len(set(MANUAL_DROP) & {it["id"] for it in pool_auto})
    gid = {it["id"]: group[i] for i, it in enumerate(items)}
    pool = [it for it in pool_auto if it["id"] in keep_ids]
    stats["final"] = len(pool)
    report["shortcuts_after_cleaning"] = shortcut_stats(pool)

    # group split, stratified by section: groups are dealt out per section until each quota is filled
    by_group = collections.defaultdict(list)
    for it in pool:
        by_group[gid[it["id"]]].append(it)
    groups = list(by_group.values())
    rng.shuffle(groups)
    sections = collections.Counter(it["section"] for it in pool)
    quota = {"eval": {s: round(c * args.n_eval / len(pool)) for s, c in sections.items()},
             "valid": {s: round(c * args.n_valid / len(pool)) for s, c in sections.items()}}
    split = {"eval": [], "valid": [], "train": []}
    got = {"eval": collections.Counter(), "valid": collections.Counter()}
    for g in groups:
        s = g[0]["section"]
        for name in ("eval", "valid"):
            if got[name][s] + len(g) <= quota[name][s] + (1 if len(g) > 1 else 0) and got[name][s] < quota[name][s]:
                split[name] += g
                got[name][s] += len(g)
                break
        else:
            split["train"] += g

    final = {}
    for name, its in split.items():
        its.sort(key=lambda x: x["id"])
        final[name] = assign_positions(its, rng)
        with open(out / f"{name}.jsonl", "w", encoding="utf-8") as f:
            for ex in final[name]:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    # leakage audit: highest question similarity between any eval item and any train/valid item
    train_q = [x["question"] for x in final["train"] + final["valid"]]
    worst = sorted(((round(max(sim(e["question"], t) for t in train_q), 2), e["id"]) for e in final["eval"]),
                   reverse=True)[:5]
    report.update({
        "counts": dict(stats),
        "splits": {k: len(v) for k, v in final.items()},
        "sections": {k: dict(collections.Counter(x["section"] for x in v)) for k, v in final.items()},
        "correct_letter": {k: dict(collections.Counter(x["letter"] for x in v)) for k, v in final.items()},
        "shortcuts": {k: shortcut_stats([{"answer": x["options"][x["answer_idx"]],
                                           "distractors": [o for i, o in enumerate(x["options"]) if i != x["answer_idx"]]}
                                          for x in v]) for k, v in final.items()},
        "eval_vs_train_max_question_similarity_top5": worst,
        "manual_drop": MANUAL_DROP,
        "related_pairs_qsim_ge_0.6": sorted(related, reverse=True),
    })
    (out / "report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print(json.dumps({k: report[k] for k in ("counts", "splits", "correct_letter", "shortcuts_before_cleaning",
                                             "shortcuts_after_cleaning", "eval_vs_train_max_question_similarity_top5")},
                     indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
