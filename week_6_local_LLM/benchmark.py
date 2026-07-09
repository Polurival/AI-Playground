#!/usr/bin/env python3

#######################################
# Before/after benchmark for local_llm_chat.py, case: short factual Q&A.
#
# "before" = base qwen2.5:3b, untuned: temp=0.7, max_tokens=500, Ollama's
#            default ctx (4096 in this Ollama version), generic system prompt
# "after"  = qwen2.5-3b-qa, the Modelfile derivative (same weights, no
#            re-download): ctx=1024, temp=0.2, max_tokens=150, factual-only
#            system prompt — see Modelfile and local_llm_chat.py header for
#            why these are baked into the model rather than passed per
#            request (Ollama's /v1 endpoint ignores per-request num_ctx).
#
# Measures per question: latency, tokens/s, answer length, correctness
# (keyword match against an expected fact) — then reports the RAM/context
# footprint of each loaded model via `ollama ps`.
#
# Usage:
#   source ../deepseek-env/bin/activate
#   python3 benchmark.py
#######################################

import subprocess
import time

from openai import OpenAI

BASE_URL = "http://localhost:11434/v1"

# (question, any one of these substrings counts as correct)
QUESTIONS = [
    ("What is the capital of France? Answer in one word.", ["paris"]),
    ("What is the chemical symbol for gold?", ["au"]),
    ("How many continents are there on Earth?", ["seven", "7"]),
    ("Who wrote the play Romeo and Juliet?", ["shakespeare"]),
    ("What is the boiling point of water in Celsius at sea level?", ["100"]),
    ("What is the largest planet in our solar system?", ["jupiter"]),
    ("In what year did World War II end?", ["1945"]),
    ("What is the square root of 64?", ["8"]),
]

CONFIGS = {
    "before (qwen2.5:3b, untuned)": {
        "model": "qwen2.5:3b",
        "system": "You are a helpful assistant",
        "temperature": 0.7,
        "max_tokens": 500,
    },
    "after (qwen2.5-3b-qa, tuned)": {
        "model": "qwen2.5-3b-qa",
        "system": None,  # baked into the model via Modelfile
        "temperature": 0.2,
        "max_tokens": 150,
    },
}

client = OpenAI(api_key="ollama", base_url=BASE_URL)


def ollama_status(model):
    """Parse `ollama ps` SIZE/CONTEXT columns for the loaded model."""
    out = subprocess.run(["ollama", "ps"], capture_output=True, text=True).stdout
    for line in out.splitlines()[1:]:
        if line.startswith(model):
            parts = line.split()
            # NAME ID SIZE_VAL SIZE_UNIT PROCESSOR%... CONTEXT UNTIL...
            size = f"{parts[2]} {parts[3]}"
            ctx = parts[6]
            return size, ctx
    return "?", "?"


def run_config(name, cfg):
    print(f"\n=== {name} ===")
    total_latency = 0.0
    total_tokens = 0
    total_words = 0
    correct = 0

    messages_base = []
    if cfg["system"]:
        messages_base.append({"role": "system", "content": cfg["system"]})

    for question, expected_any in QUESTIONS:
        start = time.monotonic()
        response = client.chat.completions.create(
            model=cfg["model"],
            messages=messages_base + [{"role": "user", "content": question}],
            stream=False,
            max_tokens=cfg["max_tokens"],
            temperature=cfg["temperature"],
        )
        elapsed = time.monotonic() - start
        answer = response.choices[0].message.content.strip()
        completion_tokens = response.usage.completion_tokens
        is_correct = any(exp.lower() in answer.lower() for exp in expected_any)

        total_latency += elapsed
        total_tokens += completion_tokens
        total_words += len(answer.split())
        correct += int(is_correct)

        mark = "OK" if is_correct else "MISS"
        print(f"[{mark}] ({elapsed:5.1f}s, {completion_tokens:3d} tok) {question}")
        print(f"       -> {answer}")

    ram_size, ram_ctx = ollama_status(cfg["model"])
    n = len(QUESTIONS)
    print(f"\n-- summary: {name} --")
    print(f"accuracy:        {correct}/{n} ({100 * correct / n:.0f}%)")
    print(f"avg latency:     {total_latency / n:.1f} s/question")
    print(f"avg tokens/s:    {total_tokens / total_latency:.1f}")
    print(f"avg answer len:  {total_words / n:.1f} words")
    print(f"ollama ps:       {ram_size} RAM, ctx={ram_ctx}")

    return {
        "accuracy": f"{correct}/{n}",
        "avg_latency_s": round(total_latency / n, 1),
        "avg_tokens_s": round(total_tokens / total_latency, 1),
        "avg_words": round(total_words / n, 1),
        "ram": ram_size,
        "ctx": ram_ctx,
    }


if __name__ == "__main__":
    print(f"Benchmarking {len(QUESTIONS)} factual Q&A prompts per config")
    results = {name: run_config(name, cfg) for name, cfg in CONFIGS.items()}

    before = results["before (qwen2.5:3b, untuned)"]
    after = results["after (qwen2.5-3b-qa, tuned)"]

    print("\n\n=== Comparison table (copy into README) ===")
    print("| Metric | Before (qwen2.5:3b, untuned) | After (qwen2.5-3b-qa, tuned) |")
    print("|---|---|---|")
    rows = [
        ("Accuracy", before["accuracy"], after["accuracy"]),
        ("Avg latency", f"{before['avg_latency_s']} s", f"{after['avg_latency_s']} s"),
        ("Avg tokens/s", before["avg_tokens_s"], after["avg_tokens_s"]),
        ("Avg answer length", f"{before['avg_words']} words", f"{after['avg_words']} words"),
        ("Context window (num_ctx)", before["ctx"], after["ctx"]),
        ("RAM (ollama ps)", before["ram"], after["ram"]),
    ]
    for metric, b, a in rows:
        print(f"| {metric} | {b} | {a} |")
