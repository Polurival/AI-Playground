#!/usr/bin/env python3
"""Замеры цены модели: размер файла, время холодной загрузки, RSS, скорость, латентность, качество на eval.

Каждый вариант = свой процесс llama-server (чистый старт). Результат: results/bench.json и results/bench.md.
  .venv/bin/python bench.py [--limit N] [--only tuned-Q4_K_M,base-Q4_K_M]
"""
import argparse
import json
import subprocess
import time
import urllib.request
from pathlib import Path

import psutil

import evalcheck
import serve

ROOT = Path(__file__).parent
VARIANTS = {
    # имя: (gguf, промпт-профиль)
    "tuned-f16": ("models/gguf/mexamen-tuned-v1-f16.gguf", "plain"),
    "tuned-Q8_0": ("models/gguf/mexamen-tuned-v1-Q8_0.gguf", "plain"),
    "tuned-Q4_K_M": ("models/gguf/mexamen-tuned-v1-Q4_K_M.gguf", "plain"),
    "base-Q4_K_M-fewshot": ("models/gguf/qwen2.5-1.5b-instruct-Q4_K_M.gguf", "fewshot"),
    "base-Q4_K_M-plain": ("models/gguf/qwen2.5-1.5b-instruct-Q4_K_M.gguf", "plain"),
}
PORT = 8110


def measure(name, gguf, profile, rows):
    path = ROOT / gguf
    t0 = time.perf_counter()
    proc = subprocess.Popen(
        [str(serve.LLAMA_SERVER), "-m", str(path), "--host", "127.0.0.1", "--port", str(PORT),
         "-c", serve.CTX, "-t", serve.THREADS, "-np", "1", "--no-webui"],
        stdout=open(ROOT / f"logs/bench-{name}.log", "wb"), stderr=subprocess.STDOUT)
    try:
        serve.Backends._wait_ready(proc, PORT)
        load_s = time.perf_counter() - t0
        rss_idle = psutil.Process(proc.pid).memory_info().rss
        m = evalcheck.run_eval(PORT, profile, rows)
        rss_peak = psutil.Process(proc.pid).memory_info().rss
    finally:
        proc.terminate()
        proc.wait(timeout=30)
    m.pop("per_question")
    return {"variant": name, "profile": profile, "size_mb": round(path.stat().st_size / 2**20, 1),
            "cold_load_s": round(load_s, 2), "rss_after_load_mb": round(rss_idle / 2**20),
            "rss_after_eval_mb": round(rss_peak / 2**20), **m}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    rows = evalcheck.load_eval(args.limit)
    names = [n for n in VARIANTS if not args.only or n in args.only.split(",")]
    out = ROOT / "results/bench.json"
    results = json.loads(out.read_text()) if out.exists() else {}
    for name in names:
        gguf, profile = VARIANTS[name]
        print(f"== {name}", flush=True)
        results[name] = measure(name, gguf, profile, rows)
        print(json.dumps(results[name]), flush=True)
        out.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    cols = ["variant", "size_mb", "cold_load_s", "rss_after_eval_mb", "decode_tokens_per_s",
            "latency_p50_s", "latency_p95_s", "avg_prompt_tokens", "avg_new_tokens", "accuracy", "strict_format"]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(str(r.get(c)) for c in cols) + " |" for r in results.values()]
    (ROOT / "results/bench.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
