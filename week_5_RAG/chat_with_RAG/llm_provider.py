"""Switchable LLM backend for the chat pipeline: DeepSeek (cloud) vs a local model served by
Ollama (analogous to `week_6_local_LLM/local_llm_chat.py` — same OpenAI-compatible endpoint,
no API key, no network).

Retrieval (query embeddings via `nomic-embed-text` + cross-encoder rerank) is untouched and
already runs entirely on this machine (see `request_to_RAG/embedder.py`). This module controls
the other half: every LLM CALL the chat makes (query rewrite, TaskState updates, final
structured answer). Switch backend at runtime with the `/model local` / `/model deepseek`
command in `main_chat.py`; everything downstream (`chat_agent.py`, `chat_generation.py`,
`task_state.py`) just asks this module for "whatever is active right now" instead of importing
a fixed client.

If DEEPSEEK_API_KEY is not set, `rag_imports` seeds a harmless placeholder so the reused
DeepSeek-authored modules don't hard-exit on import — but here the "deepseek" provider is
correctly marked unavailable, so the chat can run fully local, offline, with zero cloud calls.
"""

import logging
import os
import time

from openai import OpenAI

from rag_imports import (
    client as _DEEPSEEK_CLIENT,
    MODEL as _DEEPSEEK_MODEL,
    DEEPSEEK_KEY_PRESENT,
    REWRITE_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)

LOCAL_MODEL = os.environ.get("LOCAL_LLM_MODEL", "qwen2.5:3b")
LOCAL_BASE_URL = os.environ.get("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")
# qwen2.5:3b's Ollama default context (2048 tokens) is tight once RAG context + chat history +
# the structured-answer instructions are packed into one prompt — raise it for the local path.
LOCAL_NUM_CTX = int(os.environ.get("LOCAL_LLM_NUM_CTX", "8192"))

# Ollama ignores the API key value, but the OpenAI SDK requires a non-empty string.
_local_client = OpenAI(api_key="ollama", base_url=LOCAL_BASE_URL)

_PROVIDERS = {
    "deepseek": {
        "client": _DEEPSEEK_CLIENT,
        "model": _DEEPSEEK_MODEL,
        "label": f"deepseek ({_DEEPSEEK_MODEL}, cloud)",
        "available": DEEPSEEK_KEY_PRESENT,
    },
    "local": {
        "client": _local_client,
        "model": LOCAL_MODEL,
        "label": f"local ({LOCAL_MODEL}, Ollama @ {LOCAL_BASE_URL})",
        "available": True,
    },
}

# Default to DeepSeek when a real key is present (preserves prior behaviour for existing
# scripts/tests), otherwise fall back to local so the chat still boots with zero config.
_active = "deepseek" if DEEPSEEK_KEY_PRESENT else "local"
if not DEEPSEEK_KEY_PRESENT:
    logger.warning("[MODEL] DEEPSEEK_API_KEY not set — starting in 'local' mode, 'deepseek' provider disabled")


def set_provider(name: str) -> str:
    """Switch the active provider. Returns the new provider's label. Raises ValueError if the
    name is unknown or that provider isn't usable right now (e.g. no DeepSeek key)."""
    global _active
    name = name.strip().lower()
    if name not in _PROVIDERS:
        raise ValueError(f"unknown model '{name}' — choose 'local' or 'deepseek'")
    if not _PROVIDERS[name]["available"]:
        raise ValueError(
            "DeepSeek is unavailable: DEEPSEEK_API_KEY is not set. "
            "Export it and restart the chat, or stay on 'local'."
        )
    _active = name
    logger.info("[MODEL] active provider -> %s", _PROVIDERS[name]["label"])
    return _PROVIDERS[name]["label"]


def current_provider() -> str:
    return _active


def current_label() -> str:
    return _PROVIDERS[_active]["label"]


def available_providers() -> list[str]:
    return [name for name, p in _PROVIDERS.items() if p["available"]]


def chat_completion(messages: list[dict], max_tokens: int = 500, temperature: float = 0.2) -> str:
    """Run one chat completion against whichever provider is currently active. Returns the
    response text (empty string if the model returned nothing)."""
    provider = _PROVIDERS[_active]
    client, model = provider["client"], provider["model"]

    kwargs = dict(model=model, messages=messages, max_tokens=max_tokens, temperature=temperature)
    if _active == "local":
        kwargs["extra_body"] = {"options": {"num_ctx": LOCAL_NUM_CTX}}

    try:
        response = client.chat.completions.create(**kwargs)
    except Exception as exc:
        if _active == "local":
            raise RuntimeError(
                f"could not reach local model '{model}' at {LOCAL_BASE_URL}: {exc}. "
                f"Is Ollama running? `sudo snap start ollama` (or `ollama serve`), then "
                f"`ollama pull {model}`."
            ) from exc
        raise RuntimeError(f"DeepSeek API call failed ({provider['label']}): {exc}") from exc

    return response.choices[0].message.content or ""


def timed_chat_completion(messages: list[dict], max_tokens: int = 500, temperature: float = 0.2) -> tuple[str, float]:
    """Same as `chat_completion`, plus wall-clock seconds spent in the call — used to compare
    local vs cloud latency directly in the CLI."""
    t0 = time.perf_counter()
    text = chat_completion(messages, max_tokens=max_tokens, temperature=temperature)
    return text, time.perf_counter() - t0


def rewrite_query_active(user_query: str) -> str:
    """Query-rewrite step, routed through whichever provider is active. Behaviourally identical
    to `reranking_and_rewrite/query_rewrite.rewrite_query` (same prompt, same fallback-to-original
    on empty output) — reimplemented here only so it goes through the active client instead of
    being hardcoded to DeepSeek, which matters for a genuinely fully-local run."""
    raw = chat_completion(
        messages=[
            {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
            {"role": "user", "content": user_query},
        ],
        max_tokens=200,
        temperature=0.0,
    )
    rewritten = raw.strip().strip('"')
    if not rewritten:
        logger.warning("[REWRITE] active provider returned empty output, falling back to original query")
        return user_query
    if rewritten != user_query:
        logger.info("[REWRITE] (%s) %r -> %r", _active, user_query, rewritten)
    return rewritten
