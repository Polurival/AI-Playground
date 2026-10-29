#!/usr/bin/env python3
"""Score generate.py outputs on data/eval.jsonl; write results/summary.json, results/comparison.md, plots.

Usage: python score.py results/   (expects outputs/*.json, loss_log.json, run_info.json inside)
Accuracy uses the lenient parser (common.parse_answer); 'strict format' = exactly 'Respuesta: X) <option text>'.
"""
import json
import math
import sys
from pathlib import Path

from common import LETTERS, parse_answer

CONFIGS = [("base_plain", "База, голый запрос"), ("base_prompted", "База + проработанный промпт"),
           ("tuned_plain", "Тюн, голый запрос"), ("tuned_prompted", "Тюн + промпт")]


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def mcnemar_p(b, c):
    """Exact two-sided sign test on the discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def main():
    res = Path(sys.argv[1] if len(sys.argv) > 1 else "results")
    rows = [json.loads(line) for line in open("data/eval.jsonl", encoding="utf-8")]
    by_id = {r["id"]: r for r in rows}
    longest = {r["id"]: len(r["options"][r["answer_idx"]]) > max(len(o) for i, o in enumerate(r["options"]) if i != r["answer_idx"])
               for r in rows}

    summary, correct = {}, {}
    for name, _ in CONFIGS:
        f = res / "outputs" / f"{name}.json"
        if not f.exists():
            continue
        outs = json.loads(f.read_text())
        ok, strict, none, toks = {}, 0, 0, 0
        for o in outs:
            r = by_id[o["id"]]
            idx, st = parse_answer(o["response"], r["options"])
            ok[o["id"]] = idx == r["answer_idx"]
            strict += st
            none += idx is None
            toks += o["new_tokens"]
        n = len(outs)
        k = sum(ok.values())
        lo, hi = wilson(k, n)
        sub = lambda keep: (sum(ok[i] for i in ok if longest[i] == keep), sum(longest[i] == keep for i in ok))
        summary[name] = {"n": n, "correct": k, "accuracy": round(k / n, 3), "ci95": [round(lo, 3), round(hi, 3)],
                         "strict_format": round(strict / n, 3), "unparsed": round(none / n, 3),
                         "avg_new_tokens": round(toks / n, 1),
                         "acc_when_answer_is_longest": sub(True), "acc_when_not_longest": sub(False)}
        correct[name] = ok

    n = len(rows)
    heur = {"random (expected)": 0.25,
            "always the longest option": sum(longest.values()) / n}
    tests = {}
    for a, b in (("base_plain", "base_prompted"), ("base_prompted", "tuned_plain"), ("base_plain", "tuned_plain"),
                 ("base_prompted", "tuned_prompted")):
        if a in correct and b in correct:
            x = sum(correct[a][i] and not correct[b][i] for i in correct[a])
            y = sum(correct[b][i] and not correct[a][i] for i in correct[a])
            tests[f"{a} -> {b}"] = {"only_first_right": x, "only_second_right": y, "p_value": round(mcnemar_p(x, y), 4)}

    (res / "summary.json").write_text(json.dumps({"configs": summary, "heuristics": heur, "paired_tests": tests},
                                                 indent=1, ensure_ascii=False))
    md = ["| Конфиг | Верно | Accuracy | 95% CI | Строгий формат | Не распарсилось | Ср. токенов |", "|---|---|---|---|---|---|---|"]
    for name, label in CONFIGS:
        if name in summary:
            s = summary[name]
            md.append(f"| {label} | {s['correct']}/{s['n']} | **{s['accuracy']:.1%}** | {s['ci95'][0]:.0%}–{s['ci95'][1]:.0%} | "
                      f"{s['strict_format']:.0%} | {s['unparsed']:.0%} | {s['avg_new_tokens']} |")
    md += ["", "Эталоны без модели: " + "; ".join(f"{k} — {v:.1%}" for k, v in heur.items()), "",
           "| Конфиг | Верно, когда ответ — самый длинный вариант | Верно, когда нет |", "|---|---|---|"]
    for name, label in CONFIGS:
        if name in summary:
            s = summary[name]
            (a, b), (c, d) = s["acc_when_answer_is_longest"], s["acc_when_not_longest"]
            md.append(f"| {label} | {a}/{b} ({a / max(b, 1):.0%}) | {c}/{d} ({c / max(d, 1):.0%}) |")
    md += ["", "Парные тесты (точный знаковый тест по расходящимся парам):", ""]
    for k, v in tests.items():
        md.append(f"- {k}: только первая права {v['only_first_right']}, только вторая {v['only_second_right']}, p = {v['p_value']}")
    (res / "comparison.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))

    # per-question side-by-side for reading
    texts = {name: {o["id"]: o["response"] for o in json.loads((res / "outputs" / f"{name}.json").read_text())}
             for name in correct}
    with open(res / "answers.md", "w", encoding="utf-8") as f:
        for r in rows:
            if not all(r["id"] in t for t in texts.values()):
                continue  # partial (smoke-test) run
            f.write(f"### #{r['id']} {r['question']}\n" + "\n".join(f"{LETTERS[i]}) {o}" for i, o in enumerate(r["options"]))
                    + f"\n**верно: {r['letter']}**\n\n")
            for name in texts:
                f.write(f"- `{name}` {'OK' if correct[name][r['id']] else 'XX'}: {texts[name][r['id']][:200]!r}\n")
            f.write("\n")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    if summary:
        fig, ax = plt.subplots(figsize=(7, 3.5))
        labels = [l for nme, l in CONFIGS if nme in summary]
        vals = [summary[nme]["accuracy"] * 100 for nme, _ in CONFIGS if nme in summary]
        errs = [[summary[nme]["accuracy"] * 100 - summary[nme]["ci95"][0] * 100 for nme, _ in CONFIGS if nme in summary],
                [summary[nme]["ci95"][1] * 100 - summary[nme]["accuracy"] * 100 for nme, _ in CONFIGS if nme in summary]]
        ax.bar(range(len(vals)), vals, yerr=errs, capsize=4, color="#4c78a8")
        ax.axhline(25, ls="--", c="gray", lw=1)
        ax.set_xticks(range(len(vals)), [l.replace(", ", ",\n").replace(" + ", "\n+ ") for l in labels], fontsize=8)
        ax.set_ylabel("accuracy, %"); ax.set_ylim(0, 100)
        fig.tight_layout(); fig.savefig(res / "accuracy.png", dpi=150); plt.close(fig)
    if (res / "loss_log.json").exists():
        log = json.loads((res / "loss_log.json").read_text())
        tr = [(e["step"], e["loss"]) for e in log if "loss" in e]
        ev = [(e["step"], e["eval_loss"]) for e in log if "eval_loss" in e]
        fig, ax = plt.subplots(figsize=(6, 3.5))
        ax.plot(*zip(*tr), label="train"); ax.plot(*zip(*ev), "o-", label="valid")
        ax.set_xlabel("step"); ax.set_ylabel("loss"); ax.legend(); ax.grid(alpha=.3)
        fig.tight_layout(); fig.savefig(res / "loss_curve.png", dpi=150); plt.close(fig)


if __name__ == "__main__":
    main()
