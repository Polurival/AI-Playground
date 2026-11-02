#!/usr/bin/env python3
"""Парное сравнение «до подмены» (база + проработанный промпт) и «после» (тюн, голый запрос) на 149 eval-вопросах.

Берёт уже запущенные через serve.py бэкенды (порты из registry.json по алиасам base и tuned) —
то есть проверяется ровно то, что получает приложение. Пишет results/compare.json и results/compare.md.
"""
import json
from math import comb
from pathlib import Path

import evalcheck
import serve

ROOT = Path(__file__).parent


def sign_test_p(a_only, b_only):
    n = a_only + b_only
    k = min(a_only, b_only)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2**n) if n else 1.0


def main():
    reg = serve.registry.get()
    rows = evalcheck.load_eval()
    runs = {}
    for alias in ("base", "tuned"):
        model, spec = serve.registry.resolve(alias)
        port = spec["port"]
        print(f"== {alias} -> {model}", flush=True)
        runs[alias] = (model, evalcheck.run_eval(port, spec["prompt"], rows))
    base, tuned = runs["base"][1], runs["tuned"][1]
    ok = lambda r: [q["pred"] == q["gold"] for q in r["per_question"]]
    b, t = ok(base), ok(tuned)
    base_only = sum(x and not y for x, y in zip(b, t))
    tuned_only = sum(y and not x for x, y in zip(b, t))
    summary = {
        "models": {a: m for a, (m, _) in runs.items()},
        "metrics": {a: {k: v for k, v in r.items() if k != "per_question"} for a, (_, r) in runs.items()},
        "base_only_correct": base_only, "tuned_only_correct": tuned_only,
        "both_correct": sum(x and y for x, y in zip(b, t)), "both_wrong": sum(not x and not y for x, y in zip(b, t)),
        "sign_test_p": round(sign_test_p(base_only, tuned_only), 3),
    }
    (ROOT / "results/compare.json").write_text(json.dumps({"summary": summary, "base": base, "tuned": tuned}, ensure_ascii=False, indent=1))
    print(json.dumps(summary, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
