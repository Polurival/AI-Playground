"""DeepSeek chat completion for plain and RAG-grounded answers."""

import logging
import os
import sys

from openai import OpenAI

logger = logging.getLogger(__name__)

API_KEY = os.environ.get("DEEPSEEK_API_KEY")

if not API_KEY:
    print("Error: Please set DEEPSEEK_API_KEY environment variable")
    print("Run: export DEEPSEEK_API_KEY='your-key-here'")
    sys.exit(1)

client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.deepseek.com",
)

MODEL = "deepseek-chat"

PLAIN_SYSTEM_PROMPT = (
    "Ты полезный ассистент, отвечающий на вопросы об \"Алисе в Стране чудес\" Льюиса Кэрролла."
)

RAG_SYSTEM_PROMPT = (
    "Ты полезный ассистент. Отвечай на вопрос пользователя, основываясь ТОЛЬКО на "
    "предоставленном контексте. Если в контексте нет ответа, честно скажи, что не знаешь его, "
    "и не придумывай факты."
)


def generate_answer(question: str, context: str | None = None, language: str | None = None) -> str:
    """Call DeepSeek chat. If context is given, uses the strict RAG system prompt.

    `language`, if given, appends an explicit instruction to answer in that language
    (e.g. "English") regardless of what language the question/context is in. Default
    (None) leaves the model's natural language choice untouched — existing callers are
    unaffected.
    """
    if context is not None:
        system_prompt = RAG_SYSTEM_PROMPT
        user_content = f"Контекст:\n{context}\n\nВопрос: {question}"
    else:
        system_prompt = PLAIN_SYSTEM_PROMPT
        user_content = question

    if language:
        system_prompt = f"{system_prompt} Always answer in {language}, regardless of the language of the question or context."

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        max_tokens=1000,
        temperature=0.2,
    )
    return response.choices[0].message.content or ""
