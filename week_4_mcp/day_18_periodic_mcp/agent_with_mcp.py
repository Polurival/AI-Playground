#!/usr/bin/env python3
"""
HackerNews Digest агент с доступом к MCP-инструментам.

DeepSeek сам решает, когда собирать данные, запускать планировщик
и формировать дайджест — на основе вопросов пользователя на естественном языке.

Установка:
    pip install openai mcp httpx schedule

Запуск:
    export DEEPSEEK_API_KEY='your-key'
    python3 agent_with_mcp.py

Примеры вопросов:
    "Собери свежие данные с HackerNews"
    "Покажи дайджест за последние 12 часов"
    "Запусти планировщик каждые 30 минут"
    "Что пишут про AI на HN?"
    "Статус планировщика"
"""

import asyncio
import json
import os
import sys

from openai import OpenAI

from hn_mcp_client import call_hn_tool, list_hn_tools

API_KEY = os.environ.get("DEEPSEEK_API_KEY")

if not API_KEY:
    print("Error: Please set DEEPSEEK_API_KEY environment variable")
    print("Run: export DEEPSEEK_API_KEY='your-key-here'")
    sys.exit(1)

client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.deepseek.com",
)

HN_TOOLS_SCHEMA: list = []


def load_hn_tools() -> None:
    """Загружает MCP-инструменты HN-сервера и строит схему для DeepSeek."""
    global HN_TOOLS_SCHEMA
    try:
        tools = asyncio.run(list_hn_tools())
    except Exception as exc:
        print(f"Не удалось загрузить HN MCP-инструменты: {exc}\n")
        return

    HN_TOOLS_SCHEMA = [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.inputSchema or {"type": "object", "properties": {}},
            },
        }
        for tool in tools
    ]
    print(f"Загружено инструментов: {len(HN_TOOLS_SCHEMA)}")
    for t in HN_TOOLS_SCHEMA:
        print(f"  - {t['function']['name']}")
    print()


def _format_tool_result(result) -> str:
    parts = []
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        parts.append(text if text is not None else str(item))
    return "\n".join(parts) if parts else str(result)


def ask_agent(question: str) -> str:
    """Запрос к DeepSeek с доступом к HN MCP-инструментам.

    LLM сам решает, вызывать ли collect_now / get_digest / start_scheduler
    и с какими параметрами.
    """
    messages = [
        {
            "role": "system",
            "content": (
                "You are a HackerNews digest assistant with access to tools for collecting "
                "and analyzing HackerNews top stories. "
                "When the user asks to collect data, show digest, start/stop scheduler, or "
                "filter stories by topic — call the appropriate tool. "
                "Respond in the same language the user uses. "
                "When showing a digest, format it clearly with scores and titles."
            ),
        },
        {"role": "user", "content": question},
    ]

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        tools=HN_TOOLS_SCHEMA,
        tool_choice="auto",
        max_tokens=2000,
        temperature=0.3,
    )
    message = response.choices[0].message

    if not message.tool_calls:
        return message.content

    messages.append(message.model_dump(exclude_none=True))

    for tool_call in message.tool_calls:
        arguments = json.loads(tool_call.function.arguments or "{}")
        tool_name = tool_call.function.name
        print(f"  [tool call] {tool_name}({arguments})")

        try:
            tool_result = asyncio.run(call_hn_tool(tool_name, arguments))
            result_text = _format_tool_result(tool_result)
        except Exception as exc:
            result_text = f"Ошибка вызова {tool_name}: {exc}"

        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result_text,
            }
        )

    final = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        max_tokens=2000,
        temperature=0.3,
    )
    return final.choices[0].message.content


def main() -> None:
    print("=== HackerNews Digest Agent (DeepSeek + MCP) ===")
    print("Для выхода: exit / quit\n")
    print("Примеры:")
    print('  "Собери данные с HackerNews"')
    print('  "Покажи дайджест за последние 6 часов"')
    print('  "Что пишут про Python на HN?"')
    print('  "Запусти планировщик каждые 30 минут"')
    print('  "Статус планировщика"\n')

    load_hn_tools()

    if not HN_TOOLS_SCHEMA:
        print("Нет доступных инструментов. Проверьте hn_mcp_server.py.")
        sys.exit(1)

    while True:
        try:
            user_input = input("Вы: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nЗавершение.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            break

        answer = ask_agent(user_input)
        print(f"\nАгент: {answer}\n")


if __name__ == "__main__":
    main()
