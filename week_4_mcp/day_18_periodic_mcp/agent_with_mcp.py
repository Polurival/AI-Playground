#!/usr/bin/env python3
"""
HackerNews + Wikipedia Research Agent (DeepSeek + два MCP-сервера).

Агент оркестрирует два MCP:
  • HN MCP   — сбор, фильтрация, дайджест, сохранение историй HackerNews
  • Wiki MCP — поиск статей и получение вводных абзацев Wikipedia

Агент сам выбирает нужный инструмент, маршрутизирует вызовы между серверами
и выполняет длинные флоу: HN → Wikipedia → сохранение обогащённого отчёта.

Установка:
    pip install openai mcp httpx

Запуск:
    export DEEPSEEK_API_KEY='your-key'
    python3 agent_with_mcp.py

Примеры запросов для демонстрации оркестрации:
    "Исследуй тему Rust на HN: возьми 5 историй, найди Wikipedia-статью и сохрани отчёт"
    "Собери топ AI-историй с HN, обогати Wikipedia-контекстом и сохрани дайджест"
    "Покажи дайджест HN за 12 часов"
    "Найди в Wikipedia статью про WebAssembly"
    "Что пишут про Python на HN? Добавь Wikipedia-справку и сохрани"
"""

import asyncio
import json
import os
import sys

from openai import OpenAI

from hn_mcp_client import call_hn_tool, list_hn_tools
from wiki_mcp_client import call_wiki_tool, list_wiki_tools

API_KEY = os.environ.get("DEEPSEEK_API_KEY")

if not API_KEY:
    print("Error: Please set DEEPSEEK_API_KEY environment variable")
    print("Run: export DEEPSEEK_API_KEY='your-key-here'")
    sys.exit(1)

client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.deepseek.com",
)

ALL_TOOLS_SCHEMA: list = []
# tool_name → "hn" | "wiki"
TOOL_SERVER_MAP: dict[str, str] = {}

SYSTEM_PROMPT = """You are a HackerNews Research Assistant with access to two MCP servers:

1. **HackerNews MCP** — tools for fetching, filtering, summarizing, and saving HN top stories:
   - search_hn: fetch top HN stories (optionally filter by keyword/score) — returns JSON
   - summarize_stories: format stories JSON into readable digest text
   - save_to_file: save text content to a file in data/digests/
   - collect_now: fetch and store HN stories in the database
   - get_digest: retrieve stored stories digest with filters
   - get_stories: get raw stored stories as JSON
   - start_scheduler / stop_scheduler / get_scheduler_status: manage background collector
   - clear_old_data: remove old records from database

2. **Wikipedia MCP** — tools for searching and reading Wikipedia articles:
   - search_wikipedia: search Wikipedia by query, returns list of matching articles with titles/snippets
   - get_article_summary: get full intro paragraph and description for an article by exact title

**Orchestration rules:**
- For research/enrichment tasks: use HN tools first to get stories, then Wiki tools to add context
- For a full enriched report: search_hn → summarize_stories → search_wikipedia → get_article_summary → save_to_file
- Call tools sequentially — each step feeds into the next
- When saving enriched reports, combine HN digest + Wikipedia context into one cohesive text
- Route each tool call to its correct server automatically

Respond in the same language the user uses. Format digests clearly with scores and titles."""


def load_all_tools() -> None:
    """Загружает инструменты обоих MCP-серверов и строит общую схему + карту роутинга."""
    global ALL_TOOLS_SCHEMA, TOOL_SERVER_MAP

    servers = [
        ("hn", list_hn_tools),
        ("wiki", list_wiki_tools),
    ]

    for server_id, list_fn in servers:
        try:
            tools = asyncio.run(list_fn())
        except Exception as exc:
            print(f"[{server_id}] Не удалось загрузить инструменты: {exc}")
            continue

        print(f"[{server_id.upper()} MCP] Загружено инструментов: {len(tools)}")
        for tool in tools:
            print(f"  - {tool.name}")
            ALL_TOOLS_SCHEMA.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description or "",
                        "parameters": tool.inputSchema or {"type": "object", "properties": {}},
                    },
                }
            )
            TOOL_SERVER_MAP[tool.name] = server_id

    print(f"\nВсего инструментов: {len(ALL_TOOLS_SCHEMA)}\n")


def _format_tool_result(result) -> str:
    parts = []
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        parts.append(text if text is not None else str(item))
    return "\n".join(parts) if parts else str(result)


async def _dispatch_tool(tool_name: str, arguments: dict):
    """Маршрутизирует вызов инструмента на нужный MCP-сервер."""
    server = TOOL_SERVER_MAP.get(tool_name, "hn")
    if server == "wiki":
        return await call_wiki_tool(tool_name, arguments)
    return await call_hn_tool(tool_name, arguments)


MAX_TOOL_ROUNDS = 15


def ask_agent(question: str) -> str:
    """Запрос к DeepSeek с доступом к инструментам обоих MCP-серверов.

    Agentic loop: LLM вызывает инструменты любого сервера столько раз, сколько нужно,
    пока не вернёт финальный текстовый ответ.
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    for round_num in range(MAX_TOOL_ROUNDS):
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            tools=ALL_TOOLS_SCHEMA,
            tool_choice="auto",
            max_tokens=4000,
            temperature=0.3,
        )
        message = response.choices[0].message

        if not message.tool_calls:
            return message.content or ""

        messages.append(message.model_dump(exclude_none=True))

        for tool_call in message.tool_calls:
            arguments = json.loads(tool_call.function.arguments or "{}")
            tool_name = tool_call.function.name
            server = TOOL_SERVER_MAP.get(tool_name, "?")
            print(f"  [round {round_num + 1}] [{server.upper()}] {tool_name}({arguments})")

            try:
                tool_result = asyncio.run(_dispatch_tool(tool_name, arguments))
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

    return "Превышен лимит итераций инструментов."


def main() -> None:
    print("=== HackerNews + Wikipedia Research Agent (DeepSeek + 2 MCP) ===")
    print("Для выхода: exit / quit\n")
    print("Примеры для демонстрации оркестрации:")
    print('  "Исследуй тему Rust на HN: возьми 5 историй, найди Wikipedia-статью и сохрани отчёт"')
    print('  "Собери топ AI-историй с HN, обогати Wikipedia-контекстом и сохрани дайджест"')
    print('  "Покажи дайджест HN за 12 часов"')
    print('  "Найди в Wikipedia статью про WebAssembly"')
    print('  "Что пишут про Python на HN? Добавь Wikipedia-справку и сохрани"\n')

    load_all_tools()

    if not ALL_TOOLS_SCHEMA:
        print("Нет доступных инструментов. Проверьте серверы.")
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
