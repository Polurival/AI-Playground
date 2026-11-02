#!/usr/bin/env python3
"""Слить LoRA-адаптер Дня 7 с базой Qwen2.5-1.5B-Instruct в обычную HF-модель (fp16, safetensors).

Результат кладётся в models/hf/<name>/ — оттуда его читает convert_hf_to_gguf.py.
Запуск (CPU, ~3 GB RAM):  .venv/bin/python merge_adapter.py --name mexamen-tuned-v1
"""
import argparse
import time
from pathlib import Path

import torch
from huggingface_hub import snapshot_download
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = Path(__file__).parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="Qwen/Qwen2.5-1.5B-Instruct")
    ap.add_argument("--adapter", default=str(ROOT.parent / "fine_tuning_my_dataset/results/adapter"))
    ap.add_argument("--name", default="mexamen-tuned-v1")
    args = ap.parse_args()

    out = ROOT / "models/hf" / args.name
    base_dir = ROOT / "models/hf/qwen2.5-1.5b-instruct"
    if not (base_dir / "config.json").exists():
        snapshot_download(args.base, local_dir=base_dir, allow_patterns=["*.json", "*.safetensors", "merges.txt", "vocab.json"])

    t0 = time.time()
    tok = AutoTokenizer.from_pretrained(base_dir)
    model = AutoModelForCausalLM.from_pretrained(base_dir, dtype=torch.float16)
    model = PeftModel.from_pretrained(model, args.adapter)
    model = model.merge_and_unload()
    model.save_pretrained(out, safe_serialization=True)
    tok.save_pretrained(out)
    print(f"merged -> {out} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
