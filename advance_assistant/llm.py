"""OpenAI-compatible chat client with native tool calling."""

import logging

from openai import AsyncOpenAI

from config import AssistantConfig

logger = logging.getLogger(__name__)


def make_client(cfg: AssistantConfig) -> AsyncOpenAI:
    if not cfg.llm_api_key:
        raise RuntimeError(
            "No LLM API key found. Set ASSISTANT_LLM_API_KEY (or DEEPSEEK_API_KEY / OPENAI_API_KEY)."
        )
    return AsyncOpenAI(api_key=cfg.llm_api_key, base_url=cfg.llm_base_url)


async def chat(cfg: AssistantConfig, client: AsyncOpenAI, messages: list[dict],
               tools: list[dict] | None = None):
    """One completion; returns the response message (may carry `tool_calls`)."""
    kwargs = dict(model=cfg.llm_model, messages=messages,
                  max_tokens=cfg.max_tokens, temperature=cfg.temperature)
    if tools:
        kwargs["tools"] = tools
    try:
        resp = await client.chat.completions.create(**kwargs)
    except Exception as exc:
        raise RuntimeError(f"LLM call failed ({cfg.llm_model} @ {cfg.llm_base_url}): {exc}") from exc
    return resp.choices[0].message
