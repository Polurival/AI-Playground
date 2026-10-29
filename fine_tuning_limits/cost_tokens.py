#!/usr/bin/env python3
"""Average prompt length (tokens, Qwen chat template) for each way of asking: bare vs engineered prompt vs context.

Run once locally (needs only the tokenizer): python cost_tokens.py results/ [model]
"""
import json
import statistics
import sys
from pathlib import Path

from transformers import AutoTokenizer

from common import (fact_closed, fact_context, plain_messages, prompted_messages, style_plain, style_prompted)

res = Path(sys.argv[1] if len(sys.argv) > 1 else "results")
# Qwen2.5 sizes share one tokenizer; override with argv[2] (e.g. a locally cached 0.5B copy)
tok = AutoTokenizer.from_pretrained(sys.argv[2] if len(sys.argv) > 2 else "Qwen/Qwen2.5-1.5B-Instruct")
D = Path("data")


def avg(rows, build):
    return round(statistics.mean(len(tok(tok.apply_chat_template(build(r), tokenize=False, add_generation_prompt=True))["input_ids"])
                                 for r in rows), 1)


mc = [json.loads(l) for l in open(D / "mc_eval.jsonl", encoding="utf-8")]
st = json.load(open(D / "style_eval.json", encoding="utf-8"))
fe = json.load(open(D / "fact_eval.json", encoding="utf-8"))
out = {
    "format": {"bare": avg(mc, lambda r: plain_messages(r["question"], r["options"])),
               "prompted": avg(mc, lambda r: prompted_messages(r["question"], r["options"]))},
    "style": {"bare": avg(st, lambda r: style_plain(r["question"])), "prompted": avg(st, lambda r: style_prompted(r["question"]))},
    "facts": {"bare": avg(fe, lambda r: fact_closed(r["question"])),
              "oracle_context": avg(fe, lambda r: fact_context(r["question"], [r["statement"]])),
              "rag_top3": avg(fe, lambda r: fact_context(r["question"], r["rag_statements"]))},
}
for v in out.values():
    k = next(iter(v))
    v["overhead_x"] = {n: round(t / v[k], 1) for n, t in v.items() if n != "overhead_x" and n != k}
(res / "token_costs.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
