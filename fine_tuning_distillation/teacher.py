#!/usr/bin/env python3
"""Ask the teacher (DeepSeek API, thinking disabled so the reasoning is visible text) to solve GSM8K questions.

  python teacher.py test            # data/test.jsonl            -> data/teacher_test.jsonl  (1 attempt, T=0)
  python teacher.py train           # data/train_questions.jsonl -> data/teacher_train.jsonl (T=0, then up to
                                    #                                2 retries at T=0.7 while the answer != gold)
Raw API replies are kept as they came (content, finish_reason, usage, wall-clock latency); judging them is
filter_data.py's job. Resumable: ids already present in the output file are skipped. Key: $DEEPSEEK_API_KEY.
"""
import argparse
import json
import os
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from common import build_prompt, parse_answer, same_number

URL = "https://api.deepseek.com/chat/completions"


def call(model, question, temperature, max_tokens=700):
    body = {"model": model, "messages": [{"role": "user", "content": build_prompt(question)}],
            "temperature": temperature, "max_tokens": max_tokens, "thinking": {"type": "disabled"}}
    req = urllib.request.Request(URL, json.dumps(body).encode(), {
        "Authorization": "Bearer " + os.environ["DEEPSEEK_API_KEY"], "Content-Type": "application/json"})
    for attempt in range(6):
        t0 = time.time()
        try:
            r = json.load(urllib.request.urlopen(req, timeout=120))
            ch = r["choices"][0]
            return {"temperature": temperature, "content": ch["message"]["content"] or "",
                    "finish_reason": ch["finish_reason"], "latency_s": round(time.time() - t0, 3),
                    "usage": {k: r["usage"].get(k) for k in
                              ("prompt_tokens", "completion_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens")}}
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as e:
            time.sleep(2 ** attempt)
            err = repr(e)
    raise RuntimeError(f"API failed after retries: {err}")


def solve(model, row, retries):
    attempts = [call(model, row["question"], 0.0)]
    for _ in range(retries):
        num, strict = parse_answer(attempts[-1]["content"])
        if strict and same_number(num, row["gold"]) and attempts[-1]["finish_reason"] == "stop":
            break
        attempts.append(call(model, row["question"], 0.7))
    return {"id": row["id"], "question": row["question"], "gold": row["gold"], "steps": row["steps"],
            "model": model, "attempts": attempts}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("split", choices=["test", "train"])
    ap.add_argument("--model", default="deepseek-v4-pro")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    src = "data/test.jsonl" if args.split == "test" else "data/train_questions.jsonl"
    dst = f"data/teacher_{args.split}.jsonl"
    rows = [json.loads(l) for l in open(src, encoding="utf-8")]
    if args.limit:
        rows = rows[:args.limit]
    done = set()
    if os.path.exists(dst):
        done = {json.loads(l)["id"] for l in open(dst, encoding="utf-8")}
    todo = [r for r in rows if r["id"] not in done]
    retries = 2 if args.split == "train" else 0
    print(f"{len(rows)} rows, {len(done)} done, {len(todo)} to go; model={args.model} workers={args.workers}")
    lock, t0, n = threading.Lock(), time.time(), 0
    with open(dst, "a", encoding="utf-8") as out, ThreadPoolExecutor(args.workers) as pool:
        futs = [pool.submit(solve, args.model, r, retries) for r in todo]
        for f in as_completed(futs):
            res = f.result()
            with lock:
                out.write(json.dumps(res, ensure_ascii=False) + "\n")
                out.flush()
                n += 1
                if n % 100 == 0:
                    print(f"{n}/{len(todo)} {time.time() - t0:.0f}s", flush=True)
    print(f"done in {time.time() - t0:.0f}s -> {dst}")


if __name__ == "__main__":
    main()
