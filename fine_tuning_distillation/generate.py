#!/usr/bin/env python3
"""Run data/test.jsonl (GSM8K test) through the student before and after distillation (greedy decoding).

Configs: base (untouched student), tuned (student + LoRA adapter, merged into the weights = what you would deploy).
For each config, written to <out>/outputs/<config>.json:
  items   response, new_tokens, truncated, mean_logprob / min_logprob of the generated tokens
  meta    batched run: wall seconds, req/s, generated tokens/s, peak GPU memory
          latency bench: batch=1 on the first --bench-n questions (seconds per request, tokens/s)
Prompt = common.build_prompt(question), identical for teacher, base and tuned.
"""
import argparse
import json
import statistics
import time
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

from common import build_prompt


def encode(tok, questions, device):
    texts = [tok.apply_chat_template([{"role": "user", "content": build_prompt(q)}], tokenize=False,
                                     add_generation_prompt=True) for q in questions]
    return tok(texts, return_tensors="pt", padding=True, add_special_tokens=False).to(device)


@torch.no_grad()
def generate(model, tok, questions, max_new_tokens):
    enc = encode(tok, questions, model.device)
    gen = model.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False, temperature=None, top_p=None,
                         top_k=None, repetition_penalty=1.0, pad_token_id=tok.pad_token_id)
    out = []
    for row in gen[:, enc["input_ids"].shape[1]:]:
        ids = [t for t in row.tolist() if t != tok.pad_token_id]
        out.append(ids)
    return out


@torch.no_grad()
def logprobs(model, tok, questions, gen_ids, batch=4):
    """Teacher-forced pass over prompt+reply: per-token log-probability of the generated tokens."""
    res = []
    for i in range(0, len(questions), batch):
        qs, gs = questions[i:i + batch], gen_ids[i:i + batch]
        prompts = [tok(tok.apply_chat_template([{"role": "user", "content": build_prompt(q)}], tokenize=False,
                                               add_generation_prompt=True), add_special_tokens=False)["input_ids"]
                   for q in qs]
        width = max(len(p) + len(g) for p, g in zip(prompts, gs))
        ids = torch.full((len(qs), width), tok.pad_token_id)
        mask = torch.zeros((len(qs), width), dtype=torch.long)
        for k, (p, g) in enumerate(zip(prompts, gs)):
            ids[k, :len(p) + len(g)] = torch.tensor(p + g)
            mask[k, :len(p) + len(g)] = 1
        logits = model(input_ids=ids.to(model.device), attention_mask=mask.to(model.device)).logits
        for k, (p, g) in enumerate(zip(prompts, gs)):
            if not g:
                res.append((0.0, 0.0))
                continue
            lp = torch.log_softmax(logits[k, len(p) - 1:len(p) + len(g) - 1].float(), dim=-1)
            tok_lp = lp.gather(1, torch.tensor(g, device=lp.device)[:, None])[:, 0]
            res.append((tok_lp.mean().item(), tok_lp.min().item()))
        del logits
    return res


def run_config(name, model, tok, rows, args, out_dir):
    cuda = torch.cuda.is_available()
    questions = [r["question"] for r in rows]
    order = sorted(range(len(rows)), key=lambda i: len(rows[i]["question"]))  # similar lengths -> less padding
    gen_ids = [None] * len(rows)
    if cuda:
        torch.cuda.reset_peak_memory_stats()
        torch.cuda.synchronize()
    t0 = time.time()
    for s in range(0, len(order), args.batch):
        idx = order[s:s + args.batch]
        for i, g in zip(idx, generate(model, tok, [questions[i] for i in idx], args.max_new_tokens)):
            gen_ids[i] = g
    if cuda:
        torch.cuda.synchronize()
    wall = time.time() - t0
    peak = round(torch.cuda.max_memory_allocated() / 1e9, 2) if cuda else None
    n_tok = sum(len(g) for g in gen_ids)
    print(f"{name}: {len(rows)} questions, {wall:.0f}s, {n_tok / wall:.0f} tok/s, peak {peak} GB", flush=True)

    # latency of a single request (batch = 1), the way an interactive service would see it
    lat = []
    for q in questions[:args.bench_n]:
        if cuda:
            torch.cuda.synchronize()
        t = time.time()
        g = generate(model, tok, [q], args.max_new_tokens)[0]
        if cuda:
            torch.cuda.synchronize()
        lat.append((time.time() - t, len(g)))

    lps = logprobs(model, tok, questions, gen_ids)
    items = []
    for r, g, (mean_lp, min_lp) in zip(rows, gen_ids, lps):
        items.append({"id": r["id"], "response": tok.decode(g, skip_special_tokens=True).strip(),
                      "new_tokens": len(g), "truncated": len(g) >= args.max_new_tokens,
                      "mean_logprob": round(mean_lp, 4), "min_logprob": round(min_lp, 3)})
    meta = {"config": name, "n": len(rows), "batch": args.batch, "max_new_tokens": args.max_new_tokens,
            "gpu": torch.cuda.get_device_name(0) if cuda else "cpu", "peak_gpu_mem_gb": peak,
            "batched_wall_s": round(wall, 1), "batched_req_per_s": round(len(rows) / wall, 3),
            "batched_gen_tok_per_s": round(n_tok / wall, 1), "total_gen_tokens": n_tok,
            "bench_n": len(lat), "latency_s_median": round(statistics.median(l for l, _ in lat), 2),
            "latency_tok_per_s": round(sum(n for _, n in lat) / sum(l for l, _ in lat), 1),
            "dtype": str(model.dtype)}
    (out_dir / f"{name}.json").write_text(json.dumps({"meta": meta, "items": items}, indent=1, ensure_ascii=False))
    print(json.dumps(meta), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen2.5-0.5B-Instruct")
    ap.add_argument("--adapter", default="out/adapter")
    ap.add_argument("--eval", default="data/test.jsonl")
    ap.add_argument("--out", default="out")
    ap.add_argument("--max-new-tokens", type=int, default=512)
    ap.add_argument("--batch", type=int, default=48)
    ap.add_argument("--bench-n", type=int, default=20)
    ap.add_argument("--limit", type=int, default=0, help="only first N questions (smoke test)")
    ap.add_argument("--only", default="", help="comma list of configs to run (base,tuned)")
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(args.eval, encoding="utf-8")]
    if args.limit:
        rows = rows[:args.limit]
    cuda = torch.cuda.is_available()
    tok = AutoTokenizer.from_pretrained(args.model, padding_side="left")
    model = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.float16 if cuda else torch.float32)
    if cuda:
        model.to("cuda")
    model.eval()
    out_dir = Path(args.out) / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    only = set(filter(None, args.only.split(",")))
    if not only or "base" in only:
        run_config("base", model, tok, rows, args, out_dir)
    if not only or "tuned" in only:
        model = PeftModel.from_pretrained(model, args.adapter).merge_and_unload()
        model.eval()
        run_config("tuned", model, tok, rows, args, out_dir)


if __name__ == "__main__":
    main()
