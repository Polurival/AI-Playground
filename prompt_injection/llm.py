"""Тонкий клиент DeepSeek (OpenAI-совместимый /chat/completions) без внешних зависимостей, кроме requests."""
from __future__ import annotations

import os
import time

import requests

API_URL = "https://api.deepseek.com/chat/completions"
MODEL = os.environ.get("PI_MODEL", "deepseek-v4-flash")


def chat(messages: list[dict], temperature: float = 0.7, max_tokens: int = 500, retries: int = 4) -> str:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY не задан")
    body = {
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "thinking": {"type": "disabled"},  # обычное поведение чата, без цепочки рассуждений
    }
    return _post(API_URL, {"Authorization": f"Bearer {key}"}, body, retries, timeout=90)


def _post(url: str, headers: dict, body: dict, retries: int, timeout: int) -> str:
    for attempt in range(retries):
        try:
            r = requests.post(url, json=body, headers=headers, timeout=timeout)
            if r.status_code == 429 or r.status_code >= 500:
                raise RuntimeError(f"HTTP {r.status_code}")
            r.raise_for_status()
            return (r.json()["choices"][0]["message"]["content"] or "").strip()
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")
