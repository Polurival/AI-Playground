"""Прогон eval-вопросов Дня 7 (149 шт., не входят в обучение) через llama-server и подсчёт метрик.

Используется rollout.py (проверка перед выкаткой) и bench.py (замеры квантований/версий).
Парсер ответа и критерий «строгий формат» — те же, что в ../fine_tuning_my_dataset/common.py.
"""
import json
import statistics
import sys
import time
import urllib.request
from pathlib import Path

import prompts

DAY7 = Path(__file__).parent.parent / "fine_tuning_my_dataset"
sys.path.insert(0, str(DAY7))
import common  # noqa: E402  (parse_answer из Дня 7)

EVAL_PATH = DAY7 / "data/eval.jsonl"


def load_eval(limit=0):
    rows = [json.loads(line) for line in open(EVAL_PATH, encoding="utf-8")]
    return rows[:limit] if limit else rows


def ask(port, profile, row, max_tokens=128):
    """Один запрос напрямую в llama-server. cache_prompt выключен: честная цена каждого запроса."""
    messages = prompts.apply_profile(profile, [{"role": "user", "content": prompts.format_question(row["question"], row["options"])}])
    body = json.dumps({"messages": messages, "temperature": 0, "max_tokens": max_tokens, "cache_prompt": False}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", data=body, headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.loads(r.read())
    wall = time.perf_counter() - t0
    return data["choices"][0]["message"]["content"].strip(), wall, data.get("timings", {}), data.get("usage", {})


def run_eval(port, profile, rows):
    correct = strict = unparsed = 0
    walls, tps, prompt_tokens, new_tokens = [], [], [], []
    per_question = []
    for row in rows:
        text, wall, timings, usage = ask(port, profile, row)
        idx, ok = common.parse_answer(text, row["options"])
        correct += idx == row["answer_idx"]
        strict += ok
        unparsed += idx is None
        walls.append(wall)
        if timings.get("predicted_per_second"):
            tps.append(timings["predicted_per_second"])
        prompt_tokens.append(usage.get("prompt_tokens", 0))
        new_tokens.append(usage.get("completion_tokens", 0))
        per_question.append({"id": row["id"], "pred": idx, "gold": row["answer_idx"], "response": text})
    n = len(rows)
    walls_sorted = sorted(walls)
    return {
        "n": n,
        "accuracy": round(correct / n, 4),
        "strict_format": round(strict / n, 4),
        "unparsed": round(unparsed / n, 4),
        "latency_p50_s": round(statistics.median(walls), 3),
        "latency_p95_s": round(walls_sorted[min(n - 1, int(0.95 * n))], 3),
        "decode_tokens_per_s": round(statistics.mean(tps), 1) if tps else None,
        "avg_prompt_tokens": round(statistics.mean(prompt_tokens), 1),
        "avg_new_tokens": round(statistics.mean(new_tokens), 1),
        "per_question": per_question,
    }
