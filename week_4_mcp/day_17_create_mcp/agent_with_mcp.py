#!/usr/bin/env python3

#######################################
# Чат-агент (на основе day_16/agent_with_mcp.py), который умеет
# вызывать собственный MCP-сервер git_mcp_server.py по ключевой фразе
# или через function-calling DeepSeek.
#
# Установка:
#   pip install openai mcp
#   export DEEPSEEK_API_KEY='your-key-here'
#
# Запуск:
#   python3 agent_with_mcp.py
#
# В чате напишите, например:
#   список инструментов git
# — агент вызовет git_mcp_client.list_git_tools() вместо LLM.
#
# Или спросите про репозиторий на естественном языке:
#   "Покажи последние 5 коммитов в репозитории /path/to/repo"
# — DeepSeek сам выберет инструмент (git_log) и параметры, вызовет его
# через MCP и ответит на основе реального результата.
#######################################

import asyncio
import json
import os
import sys
from pathlib import Path

from openai import OpenAI

from git_mcp_client import call_git_tool, list_git_tools

API_KEY = os.environ.get("DEEPSEEK_API_KEY")

if not API_KEY:
    print("Error: Please set DEEPSEEK_API_KEY environment variable")
    print("Run: export DEEPSEEK_API_KEY='your-key-here'")
    sys.exit(1)

client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.deepseek.com",
)

# Репозиторий, с которым работает агент по умолчанию (корень этого проекта)
DEFAULT_REPO_PATH = str(Path(__file__).resolve().parents[2])

# Триггерные фразы, по которым вместо LLM вызывается git MCP-сервер
GIT_TOOLS_TRIGGERS = (
    "список инструментов git",
    "git tools",
    "list git tools",
)

# Схема инструментов git в формате OpenAI function-calling,
# заполняется один раз при старте через load_git_tools()
GIT_TOOLS_SCHEMA: list = []


def load_git_tools() -> None:
    """Загружает реальные MCP-инструменты git-сервера и строит function-схему для DeepSeek."""
    global GIT_TOOLS_SCHEMA
    try:
        tools = asyncio.run(list_git_tools())
    except Exception as exc:
        print(f"Не удалось загрузить инструменты git MCP-сервера: {exc}\n")
        return

    GIT_TOOLS_SCHEMA = [
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


def _format_tool_result(result) -> str:
    """Превращает CallToolResult MCP в текст для передачи обратно в LLM."""
    parts = []
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        parts.append(text if text is not None else str(item))
    return "\n".join(parts) if parts else str(result)


def ask_deepseek_with_git_tools(question: str) -> str:
    """Запрос к DeepSeek с доступом к реальным MCP-инструментам git.

    LLM сам решает, нужно ли вызвать инструмент (например git_log, git_diff),
    и сам подставляет параметры (путь к репозиторию, число коммитов и т.д.).
    """
    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful assistant with access to a local git repository "
                f"via tools. Default repo_path if the user doesn't specify one: "
                f"{DEFAULT_REPO_PATH}. When the user asks about commits, branches, "
                "diffs, or repository status, call the appropriate git tool."
            ),
        },
        {"role": "user", "content": question},
    ]

    response = client.chat.completions.create(
        model="deepseek-v4-flash",
        messages=messages,
        tools=GIT_TOOLS_SCHEMA,
        tool_choice="auto",
        max_tokens=1000,
        temperature=0.7,
    )
    message = response.choices[0].message

    if not message.tool_calls:
        return message.content

    # Модель решила вызвать один или несколько MCP-инструментов git
    messages.append(message.model_dump(exclude_none=True))
    for tool_call in message.tool_calls:
        arguments = json.loads(tool_call.function.arguments or "{}")
        try:
            tool_result = asyncio.run(call_git_tool(tool_call.function.name, arguments))
            result_text = _format_tool_result(tool_result)
        except Exception as exc:
            result_text = f"Ошибка вызова инструмента {tool_call.function.name}: {exc}"

        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result_text,
            }
        )

    # Второй запрос: даём модели результаты инструментов, чтобы получить финальный ответ
    final_response = client.chat.completions.create(
        model="deepseek-v4-flash",
        messages=messages,
        max_tokens=1000,
        temperature=0.7,
    )
    return final_response.choices[0].message.content


def ask_deepseek(question: str) -> str:
    """Обычный запрос к DeepSeek без доступа к инструментам."""
    response = client.chat.completions.create(
        model="deepseek-v4-flash",
        messages=[
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": question},
        ],
        stream=False,
        max_tokens=1000,
        temperature=0.7,
    )
    return response.choices[0].message.content


async def handle_git_tools_request() -> str:
    """Вызывает git MCP-сервер и форматирует список инструментов."""
    try:
        tools = await list_git_tools()
    except Exception as exc:
        return f"Не удалось получить список инструментов git: {exc}"

    if not tools:
        return "Git MCP вернул пустой список инструментов."

    lines = [f"Доступно инструментов git: {len(tools)}"]
    for tool in tools:
        lines.append(f"- {tool.name}: {tool.description or 'без описания'}")
    return "\n".join(lines)


def is_git_tools_request(text: str) -> bool:
    """Проверяет, просит ли пользователь список инструментов git."""
    lowered = text.lower()
    return any(trigger in lowered for trigger in GIT_TOOLS_TRIGGERS)


def main() -> None:
    print("Чат с агентом (DeepSeek). Для выхода введите 'exit' или 'quit'.")
    print('Подсказка: напишите "список инструментов git", чтобы вызвать MCP-сервер.')
    print(f'Или спросите что-нибудь про репозиторий: "Какой статус у репозитория {DEFAULT_REPO_PATH}?"\n')

    load_git_tools()

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

        if is_git_tools_request(user_input):
            # Перехватываем запрос и обращаемся к MCP-серверу вместо LLM
            answer = asyncio.run(handle_git_tools_request())
        elif GIT_TOOLS_SCHEMA:
            # Есть доступ к MCP-инструментам git — даём LLM решить,
            # нужно ли вызвать git_log/git_status/git_diff и с какими параметрами
            answer = ask_deepseek_with_git_tools(user_input)
        else:
            answer = ask_deepseek(user_input)

        print(f"Агент: {answer}\n")


if __name__ == "__main__":
    main()
