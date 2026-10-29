#!/usr/bin/env python3
"""Run data/eval.jsonl through the base model and base+LoRA adapter (greedy decoding).

Four configs: base_plain, base_prompted, tuned_plain, tuned_prompted.
  plain    = bare question + options (what the adapter was trained on)
  prompted = system rules + 3 few-shot turns (see common.py)
Writes <config>.json into --out/outputs.
"""
import argparse
import json
import time
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

from common import plain_messages, prompted_messages


def run(model, tok, rows, build, max_new_tokens, batch):
    results = []
    for i in range(0, len(rows), batch):
        chunk = rows[i:i + batch]
        texts = [tok.apply_chat_template(build(r["question"], r["options"]), tokenize=False,
                                         add_generation_prompt=True) for r in chunk]
        enc = tok(texts, return_tensors="pt", padding=True, add_special_tokens=False).to(model.device)
        with torch.no_grad():
            gen = model.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False,
                                 temperature=None, top_p=None, top_k=None, repetition_penalty=1.0,
                                 pad_token_id=tok.pad_token_id)
        for r, row in zip(chunk, gen):
            new = row[enc["input_ids"].shape[1]:]
            n = int((new != tok.pad_token_id).sum())
            results.append({"id": r["id"], "response": tok.decode(new, skip_special_tokens=True).strip(),
                            "new_tokens": n, "truncated": n >= max_new_tokens})
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen2.5-1.5B-Instruct")
    ap.add_argument("--adapter", default="out/adapter")
    ap.add_argument("--eval", default="data/eval.jsonl")
    ap.add_argument("--out", default="out")
    ap.add_argument("--max-new-tokens", type=int, default=128)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0, help="only first N questions (smoke test)")
    ap.add_argument("--only", default="", help="comma list of configs to run")
    args = ap.parse_args()

    rows = [json.loads(line) for line in open(args.eval, encoding="utf-8")]
    if args.limit:
        rows = rows[:args.limit]
    cuda = torch.cuda.is_available()
    dtype = torch.float16 if cuda else torch.float32
    tok = AutoTokenizer.from_pretrained(args.model, padding_side="left")
    model = AutoModelForCausalLM.from_pretrained(args.model, dtype=dtype)
    if cuda:
        model.to("cuda")
    model.eval()

    out = Path(args.out) / "outputs"
    out.mkdir(parents=True, exist_ok=True)
    only = set(filter(None, args.only.split(",")))
    builders = {"plain": plain_messages, "prompted": prompted_messages}

    def do(prefix, model):
        for kind, build in builders.items():
            name = f"{prefix}_{kind}"
            if only and name not in only:
                continue
            t0 = time.time()
            res = run(model, tok, rows, build, args.max_new_tokens, args.batch)
            (out / f"{name}.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
            print(f"{name} done in {time.time() - t0:.0f}s")

    do("base", model)
    model = PeftModel.from_pretrained(model, args.adapter)
    model.eval()
    do("tuned", model)


if __name__ == "__main__":
    main()
