#!/usr/bin/env python3
"""Generate answers for every (suite, adapter, mode) in PLAN with greedy decoding.

Suites: mc_eval (Mexamen MC, day 7), ood (64 out-of-domain prompts), style_eval (open questions, 'tutor amigable'),
fact_eval (invented facts: same / paraphrased / reversed questions).
Writes <out>/outputs/<suite>__<adapter>__<mode>.json; existing files are kept unless --force.
"""
import argparse
import json
import time
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

from common import (fact_closed, fact_context, plain_messages, prompted_messages, style_plain,
                    style_prompted)

D = Path("data")
SUITES = {
    "mc_eval": dict(load=lambda: [json.loads(l) for l in open(D / "mc_eval.jsonl", encoding="utf-8")], max_new=128,
                    build={"plain": lambda r: plain_messages(r["question"], r["options"]),
                           "prompted": lambda r: prompted_messages(r["question"], r["options"])}),
    "ood": dict(load=lambda: json.load(open(D / "ood_eval.json", encoding="utf-8")), max_new=200,
                build={"plain": lambda r: [{"role": "user", "content": r["prompt"]}]}),
    "style_eval": dict(load=lambda: json.load(open(D / "style_eval.json", encoding="utf-8")), max_new=128,
                       build={"plain": lambda r: style_plain(r["question"]),
                              "prompted": lambda r: style_prompted(r["question"])}),
    "fact_eval": dict(load=lambda: json.load(open(D / "fact_eval.json", encoding="utf-8")), max_new=100,
                      build={"closed": lambda r: fact_closed(r["question"]),
                             "oracle": lambda r: fact_context(r["question"], [r["statement"]]),
                             "rag": lambda r: fact_context(r["question"], r["rag_statements"])}),
}
MC10 = ["mc10_e1", "mc10_e3", "mc10_e5", "mc10_e10"]
PLAN = [
    ("mc_eval", "base", "plain"), ("mc_eval", "base", "prompted"), ("mc_eval", "mc3", "plain"),
    *[("mc_eval", a, "plain") for a in MC10], ("mc_eval", "know", "plain"),
    ("ood", "base", "plain"), ("ood", "mc3", "plain"), *[("ood", a, "plain") for a in MC10],
    ("ood", "style", "plain"), ("ood", "know", "plain"),
    ("style_eval", "base", "plain"), ("style_eval", "base", "prompted"), ("style_eval", "style", "plain"),
    ("style_eval", "style", "prompted"), ("style_eval", "mc3", "plain"),
    ("fact_eval", "base", "closed"), ("fact_eval", "base", "oracle"), ("fact_eval", "base", "rag"),
    ("fact_eval", "know", "closed"), ("fact_eval", "know", "oracle"), ("fact_eval", "mc3", "closed"),
]


def adapter_paths(root):
    p = {"mc3": root / "mc3" / "adapter", "style": root / "style" / "adapter", "know": root / "know" / "adapter",
         "mc10_e10": root / "mc10" / "adapter"}
    for e in (1, 3, 5):
        p[f"mc10_e{e}"] = root / "mc10" / f"ckpt_ep{e}"
    return {k: v for k, v in p.items() if v.exists()}


def generate(model, tok, rows, build, max_new, batch):
    out = []
    for i in range(0, len(rows), batch):
        chunk = rows[i:i + batch]
        texts = [tok.apply_chat_template(build(r), tokenize=False, add_generation_prompt=True) for r in chunk]
        enc = tok(texts, return_tensors="pt", padding=True, add_special_tokens=False).to(model.device)
        with torch.no_grad():
            gen = model.generate(**enc, max_new_tokens=max_new, do_sample=False, temperature=None, top_p=None,
                                 top_k=None, repetition_penalty=1.0, pad_token_id=tok.pad_token_id)
        for r, row in zip(chunk, gen):
            new = row[enc["input_ids"].shape[1]:]
            n = int((new != tok.pad_token_id).sum())
            out.append({"id": r["id"], "response": tok.decode(new, skip_special_tokens=True).strip(),
                        "new_tokens": n, "truncated": n >= max_new})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen2.5-1.5B-Instruct")
    ap.add_argument("--root", default="out", help="folder with mc3/, mc10/, style/, know/ training outputs")
    ap.add_argument("--out", default="out")
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--limit", type=int, default=0, help="first N rows per suite (smoke test)")
    ap.add_argument("--only", default="", help="comma list of suites")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    cuda = torch.cuda.is_available()
    tok = AutoTokenizer.from_pretrained(args.model, padding_side="left")
    model = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.float16 if cuda else torch.float32)
    if cuda:
        model.to("cuda")
    paths = adapter_paths(Path(args.root))
    print("adapters found:", sorted(paths))
    for i, (name, p) in enumerate(paths.items()):
        if i == 0:
            model = PeftModel.from_pretrained(model, p, adapter_name=name)
        else:
            model.load_adapter(p, adapter_name=name)
    model.eval()

    out = Path(args.out) / "outputs"
    out.mkdir(parents=True, exist_ok=True)
    only = set(filter(None, args.only.split(",")))
    data = {}
    for suite, adapter, mode in PLAN:
        if only and suite not in only:
            continue
        if adapter != "base" and adapter not in paths:
            print(f"skip {suite}/{adapter}/{mode}: adapter missing")
            continue
        f = out / f"{suite}__{adapter}__{mode}.json"
        if f.exists() and not args.force:
            continue
        cfg = SUITES[suite]
        rows = data.setdefault(suite, cfg["load"]())
        rows = rows[:args.limit] if args.limit else rows
        t0 = time.time()
        if adapter == "base":
            if paths:
                with model.disable_adapter():
                    res = generate(model, tok, rows, cfg["build"][mode], cfg["max_new"], args.batch)
            else:
                res = generate(model, tok, rows, cfg["build"][mode], cfg["max_new"], args.batch)
        else:
            model.set_adapter(adapter)
            res = generate(model, tok, rows, cfg["build"][mode], cfg["max_new"], args.batch)
        f.write_text(json.dumps(res, indent=1, ensure_ascii=False))
        print(f"{f.name} done in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
