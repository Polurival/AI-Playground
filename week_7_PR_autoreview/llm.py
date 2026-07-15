"""OpenAI-compatible chat client for the reviewer.

Standalone and provider-agnostic: point ``AUTOREVIEW_LLM_BASE_URL`` / ``AUTOREVIEW_LLM_MODEL`` at
DeepSeek (default), OpenAI, or any OpenAI-compatible gateway, and supply the key via
``AUTOREVIEW_LLM_API_KEY`` / ``DEEPSEEK_API_KEY`` / ``OPENAI_API_KEY``.
"""

import logging

from openai import OpenAI

from config import ReviewConfig

logger = logging.getLogger(__name__)


def make_client(cfg: ReviewConfig) -> OpenAI:
    key = cfg.llm_api_key
    if not key:
        raise RuntimeError(
            "No LLM API key found. Set AUTOREVIEW_LLM_API_KEY (or DEEPSEEK_API_KEY / OPENAI_API_KEY)."
        )
    return OpenAI(api_key=key, base_url=cfg.llm_base_url)


def chat(cfg: ReviewConfig, client: OpenAI, system: str, user: str,
         max_tokens: int = 1600, temperature: float = 0.2) -> str:
    try:
        resp = client.chat.completions.create(
            model=cfg.llm_model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
    except Exception as exc:
        raise RuntimeError(f"LLM call failed ({cfg.llm_model} @ {cfg.llm_base_url}): {exc}") from exc
    return resp.choices[0].message.content or ""
