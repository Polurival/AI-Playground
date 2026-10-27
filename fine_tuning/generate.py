#!/usr/bin/env python3
"""Run eval_prompts.json through the base model and base+LoRA adapter (greedy decoding).

Writes base_outputs.json and tuned_outputs.json into --out.
"""
import argparse
import json
import time
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


def run(model, tok, prompts, max_new_tokens, batch):
    results = []
    for i in range(0, len(prompts), batch):
        chunk = prompts[i:i + batch]
        texts = [tok.apply_chat_template(p["messages"], tokenize=False, add_generation_prompt=True)
                 for p in chunk]
        enc = tok(texts, return_tensors="pt", padding=True, add_special_tokens=False).to(model.device)
        with torch.no_grad():
            gen = model.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False,
                                 temperature=None, top_p=None, top_k=None, repetition_penalty=1.0,
                                 pad_token_id=tok.pad_token_id)
        for p, row in zip(chunk, gen):
            new = row[enc["input_ids"].shape[1]:]
            results.append({"id": p["id"], "category": p["category"],
                            "response": tok.decode(new, skip_special_tokens=True).strip(),
                            "new_tokens": int((new != tok.pad_token_id).sum()),
                            "truncated": bool((new != tok.pad_token_id).sum() >= max_new_tokens)})
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen2.5-1.5B-Instruct")
    ap.add_argument("--adapter", default="out/adapter")
    ap.add_argument("--prompts", default="eval_prompts.json")
    ap.add_argument("--out", default="out")
    ap.add_argument("--max-new-tokens", type=int, default=350)
    ap.add_argument("--batch", type=int, default=5)
    ap.add_argument("--limit", type=int, default=0, help="only first N prompts (smoke test)")
    args = ap.parse_args()

    prompts = json.load(open(args.prompts, encoding="utf-8"))
    if args.limit:
        prompts = prompts[:args.limit]
    cuda = torch.cuda.is_available()
    dtype = torch.float16 if cuda else torch.float32
    tok = AutoTokenizer.from_pretrained(args.model, padding_side="left")
    model = AutoModelForCausalLM.from_pretrained(args.model, dtype=dtype)
    if cuda:
        model.to("cuda")
    model.eval()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    (out / "base_outputs.json").write_text(json.dumps(
        run(model, tok, prompts, args.max_new_tokens, args.batch), indent=1, ensure_ascii=False))
    print(f"base done in {time.time() - t0:.0f}s")

    model = PeftModel.from_pretrained(model, args.adapter)
    model.eval()
    t0 = time.time()
    (out / "tuned_outputs.json").write_text(json.dumps(
        run(model, tok, prompts, args.max_new_tokens, args.batch), indent=1, ensure_ascii=False))
    print(f"tuned done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
