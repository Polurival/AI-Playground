#!/usr/bin/env python3
"""Turn data/teacher_train.jsonl (raw teacher replies) into the student's training set.

For every question the attempts are tried in order and the first one that passes ALL checks is kept:
  finish    API finish_reason == stop (not cut by max_tokens)
  format    last line is exactly 'Answer: <number>', the only 'Answer:' in the text
  gold      that number equals the GSM8K reference answer
  language  no CJK / Cyrillic characters (teacher drifting out of English)
  markdown  no markdown / LaTeX (the prompt forbids it; keeps the student's targets uniform)
  length    30..1200 characters
  arith     every 'a op b = r' written in the text is arithmetically right (right final answer reached
            through a wrong intermediate step is still a bad training example)
  repeat    no line repeated verbatim
Questions without a passing attempt are dropped. Test questions never appear here (select_questions.py).
Writes data/train.jsonl, data/valid.jsonl (rows: id, messages), data/filter_report.json, data/review_sample.md.
"""
import json
import random
import re
from collections import Counter
from statistics import mean, median

from common import bad_equations, build_prompt, parse_answer, same_number

SEED, N_VALID = 42, 100
MARKDOWN = re.compile(r"\*\*|\\\(|\\\)|\\\[|\\\]|\$\$|\\frac|\\times|\\text|^#{1,6} |`", re.M)
FOREIGN = re.compile(r"[぀-ヿ㐀-鿿Ѐ-ӿ]")


def check(row, att):
    """Name of the first failed check, or None."""
    text = att["content"].strip()
    if att["finish_reason"] != "stop":
        return "finish"
    num, strict = parse_answer(text)
    if not strict:
        return "format"
    if not same_number(num, row["gold"]):
        return "gold"
    if FOREIGN.search(text):
        return "language"
    if MARKDOWN.search(text):
        return "markdown"
    if not 30 <= len(text) <= 1200:
        return "length"
    if bad_equations(text):
        return "arith"
    lines = [l.strip() for l in text.splitlines() if len(l.strip()) > 8]
    if len(lines) != len(set(lines)):
        return "repeat"
    return None


def main():
    rows = [json.loads(l) for l in open("data/teacher_train.jsonl", encoding="utf-8")]
    rows.sort(key=lambda r: r["id"])
    kept, dropped = [], []
    first_fail, final_fail = Counter(), Counter()
    recovered = 0
    for r in rows:
        fails = [check(r, a) for a in r["attempts"]]
        first_fail[fails[0] or "ok"] += 1
        ok = next((i for i, f in enumerate(fails) if f is None), None)
        if ok is None:
            final_fail[fails[-1]] += 1
            dropped.append((r, fails))
        else:
            recovered += ok > 0
            kept.append((r, r["attempts"][ok], ok))

    rng = random.Random(SEED)
    order = list(range(len(kept)))
    rng.shuffle(order)
    valid_idx = set(order[:N_VALID])
    out = {"train": [], "valid": []}
    for i, (r, att, _) in enumerate(kept):
        out["valid" if i in valid_idx else "train"].append({"id": r["id"], "steps": r["steps"], "messages": [
            {"role": "user", "content": build_prompt(r["question"])},
            {"role": "assistant", "content": att["content"].strip()}]})
    for name, items in out.items():
        with open(f"data/{name}.jsonl", "w", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")

    steps = lambda items: dict(sorted(Counter(min(i, 8) for i in items).items()))
    toks = [a["usage"]["completion_tokens"] for _, a, _ in kept]
    n_attempts = sum(len(r["attempts"]) for r in rows)
    report = {
        "questions_sent": len(rows), "api_attempts": n_attempts,
        "first_attempt_result": dict(first_fail),
        "recovered_by_retry": recovered,
        "kept": len(kept), "dropped": len(dropped), "dropped_by_last_attempt": dict(final_fail),
        "train": len(out["train"]), "valid": len(out["valid"]),
        "steps_hist_kept(8=8+)": steps(r["steps"] for r, _, _ in kept),
        "steps_hist_dropped": steps(r["steps"] for r, _ in dropped),
        "teacher_completion_tokens_kept": {"mean": round(mean(toks), 1), "median": median(toks), "max": max(toks)},
        "teacher_api_cost_usd_peak_price": round(sum(
            (a["usage"]["prompt_cache_hit_tokens"] * 0.044 + a["usage"]["prompt_cache_miss_tokens"] * 1.32
             + a["usage"]["completion_tokens"] * 3.96) / 1e6 for r in rows for a in r["attempts"]), 2),
    }
    json.dump(report, open("data/filter_report.json", "w"), indent=1)
    print(json.dumps(report, indent=1))

    with open("data/review_sample.md", "w", encoding="utf-8") as f:
        f.write("# 30 random kept examples (seed 42)\n\n")
        for i in rng.sample(range(len(kept)), min(30, len(kept))):
            r, att, k = kept[i]
            f.write(f"## {r['id']} (attempt {k + 1}, gold {r['gold']:g})\n\n{r['question']}\n\n```\n{att['content'].strip()}\n```\n\n")
        f.write("# Dropped (up to 25, with the failed checks per attempt)\n\n")
        for r, fails in dropped[:25]:
            f.write(f"## {r['id']} gold {r['gold']:g}, fails {fails}\n\n{r['question']}\n\n```\n{r['attempts'][-1]['content'].strip()}\n```\n\n")
        arith = [(r, a) for r in rows for a in r["attempts"] if check(r, a) == "arith"][:15]
        f.write("# Arithmetic-check failures (up to 15; right final answer, wrong equation in the text)\n\n")
        for r, a in arith:
            f.write(f"## {r['id']} bad: {bad_equations(a['content'])}\n\n```\n{a['content'].strip()}\n```\n\n")


if __name__ == "__main__":
    main()
