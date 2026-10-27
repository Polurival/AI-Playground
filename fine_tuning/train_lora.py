#!/usr/bin/env python3
"""LoRA fine-tune of a small chat model on a pirate-speak chat dataset.

Dataset: winglian/pirate-ultrachat-10k (messages format, ~99.6% pirate replies).
Only assistant tokens contribute to the loss; prompts are masked with -100.
Writes into --out: adapter/, loss_log.json, run_info.json.
"""
import argparse
import json
import platform
import random
import time
from pathlib import Path

import torch
import transformers
import peft
from huggingface_hub import hf_hub_download
from peft import LoraConfig, get_peft_model
from transformers import (AutoModelForCausalLM, AutoTokenizer, Trainer,
                          TrainingArguments)

DATASET = "winglian/pirate-ultrachat-10k"


def encode(tok, messages, max_len):
    """Chat-template one (user -> assistant) pair; return ids + labels or None if too long."""
    prompt = tok.apply_chat_template(messages[:-1], tokenize=False, add_generation_prompt=True)
    prompt_ids = tok(prompt, add_special_tokens=False)["input_ids"]
    reply = messages[-1]["content"].strip() + tok.eos_token
    reply_ids = tok(reply, add_special_tokens=False)["input_ids"]
    ids = prompt_ids + reply_ids
    if len(ids) > max_len:
        return None
    return {"input_ids": ids, "labels": [-100] * len(prompt_ids) + reply_ids}


def build_dataset(tok, n_train, n_val, max_len, seed):
    path = hf_hub_download(DATASET, "train.jsonl", repo_type="dataset")
    rows = [json.loads(line)["messages"] for line in open(path, encoding="utf-8")]
    random.Random(seed).shuffle(rows)
    out, skipped = [], 0
    for msgs in rows:
        ex = encode(tok, msgs, max_len)
        if ex is None:
            skipped += 1
            continue
        out.append(ex)
        if len(out) == n_train + n_val:
            break
    return out[:n_train], out[n_train:], skipped


class Collator:
    def __init__(self, pad_id):
        self.pad_id = pad_id

    def __call__(self, batch):
        width = max(len(b["input_ids"]) for b in batch)
        ids, labels, mask = [], [], []
        for b in batch:
            pad = width - len(b["input_ids"])
            ids.append(b["input_ids"] + [self.pad_id] * pad)
            labels.append(b["labels"] + [-100] * pad)
            mask.append([1] * len(b["input_ids"]) + [0] * pad)
        return {"input_ids": torch.tensor(ids), "labels": torch.tensor(labels),
                "attention_mask": torch.tensor(mask)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen2.5-1.5B-Instruct")
    ap.add_argument("--out", default="out")
    ap.add_argument("--n-train", type=int, default=1600)
    ap.add_argument("--n-val", type=int, default=100)
    ap.add_argument("--max-len", type=int, default=512)
    ap.add_argument("--epochs", type=float, default=1)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--accum", type=int, default=4)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--rank", type=int, default=8)
    ap.add_argument("--alpha", type=int, default=16)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cuda = torch.cuda.is_available()
    # T4 (sm_75) has no native bf16 -> fp16 mixed precision; Ampere+ -> bf16.
    use_bf16 = cuda and torch.cuda.get_device_capability()[0] >= 8
    use_fp16 = cuda and not use_bf16
    dtype = torch.bfloat16 if use_bf16 else torch.float16 if use_fp16 else torch.float32
    transformers.set_seed(args.seed)

    tok = AutoTokenizer.from_pretrained(args.model)
    train, val, skipped = build_dataset(tok, args.n_train, args.n_val, args.max_len, args.seed)
    n_tokens = sum(len(e["input_ids"]) for e in train)
    n_loss_tokens = sum(sum(l != -100 for l in e["labels"]) for e in train)
    print(f"train={len(train)} val={len(val)} skipped_too_long={skipped} "
          f"tokens={n_tokens} loss_tokens={n_loss_tokens}")

    model = AutoModelForCausalLM.from_pretrained(args.model, dtype=dtype)
    model.config.use_cache = False
    model.enable_input_require_grads()  # needed for gradient checkpointing with frozen embeddings
    model = get_peft_model(model, LoraConfig(
        r=args.rank, lora_alpha=args.alpha, lora_dropout=0.05, task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]))
    for p in model.parameters():  # fp16 grads cannot be unscaled -> keep trainable LoRA weights in fp32
        if p.requires_grad:
            p.data = p.data.float()
    n_trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    n_total = sum(p.numel() for p in model.parameters())
    print(f"trainable params: {n_trainable:,} / {n_total:,} ({100 * n_trainable / n_total:.2f}%)")

    steps_per_epoch = max(1, len(train) // (args.batch * args.accum))
    total_steps = int(steps_per_epoch * args.epochs)
    train_args = TrainingArguments(
        output_dir=str(out / "ckpt"), per_device_train_batch_size=args.batch,
        per_device_eval_batch_size=args.batch, gradient_accumulation_steps=args.accum,
        num_train_epochs=args.epochs, learning_rate=args.lr, lr_scheduler_type="cosine",
        warmup_steps=max(1, int(0.05 * total_steps)), weight_decay=0.0,
        logging_steps=5, eval_strategy="steps", eval_steps=max(1, total_steps // 4),
        save_strategy="no", report_to="none", seed=args.seed,
        fp16=use_fp16, bf16=use_bf16, gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        remove_unused_columns=False, dataloader_num_workers=2 if cuda else 0,
        use_cpu=not cuda)
    trainer = Trainer(model=model, args=train_args, train_dataset=train, eval_dataset=val,
                      data_collator=Collator(tok.pad_token_id))

    base_eval = trainer.evaluate()  # step 0: val loss of the untouched base model (LoRA B=0)
    print("base val loss:", base_eval["eval_loss"])
    if cuda:
        torch.cuda.reset_peak_memory_stats()
    t0 = time.time()
    result = trainer.train()
    train_seconds = time.time() - t0
    final_eval = trainer.evaluate()

    model.save_pretrained(out / "adapter")
    adapter_mb = sum(f.stat().st_size for f in (out / "adapter").glob("*")) / 1e6
    log = [{"step": 0, "eval_loss": base_eval["eval_loss"]}] + trainer.state.log_history
    (out / "loss_log.json").write_text(json.dumps(log, indent=1))
    info = {
        "base_model": args.model, "dataset": DATASET, "method": "LoRA (fp16/bf16 base, no quantization)",
        "gpu": torch.cuda.get_device_name(0) if cuda else "cpu",
        "gpu_mem_total_gb": round(torch.cuda.get_device_properties(0).total_memory / 1e9, 1) if cuda else None,
        "peak_gpu_mem_gb": round(torch.cuda.max_memory_allocated() / 1e9, 2) if cuda else None,
        "precision": str(dtype), "python": platform.python_version(), "torch": torch.__version__,
        "transformers": transformers.__version__, "peft": peft.__version__,
        "n_train": len(train), "n_val": len(val), "skipped_too_long": skipped, "max_len": args.max_len,
        "train_tokens_per_epoch": n_tokens, "loss_tokens_per_epoch": n_loss_tokens,
        "epochs": args.epochs, "per_device_batch": args.batch, "grad_accum": args.accum,
        "effective_batch": args.batch * args.accum, "optimizer_steps": result.global_step,
        "lr": args.lr, "lr_scheduler": "cosine", "warmup_steps": train_args.warmup_steps,
        "lora_r": args.rank, "lora_alpha": args.alpha, "lora_dropout": 0.05,
        "lora_targets": "q,k,v,o,gate,up,down", "trainable_params": n_trainable,
        "total_params": n_total, "seed": args.seed,
        "train_seconds": round(train_seconds, 1), "train_minutes": round(train_seconds / 60, 1),
        "final_train_loss_avg": result.training_loss,
        "val_loss_before": base_eval["eval_loss"], "val_loss_after": final_eval["eval_loss"],
        "adapter_size_mb": round(adapter_mb, 1),
    }
    (out / "run_info.json").write_text(json.dumps(info, indent=1))
    print(json.dumps(info, indent=1))


if __name__ == "__main__":
    main()
