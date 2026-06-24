#!/usr/bin/env python3

#######################################
# Простой чат-агент (на основе test_deepseek_task_2.py), который умеет
# вызывать MCP-сервер Google Calendar по ключевой фразе в сообщении.
#
# Установка:
#   pip install openai mcp
#   export DEEPSEEK_API_KEY='your-key-here'
#   export GOOGLE_ACCESS_TOKEN='your-google-access-token'
#
# Запуск:
#   python3 agent_with_mcp.py
#
# В чате напишите, например:
#   список инструментов google calendar
# — агент вызовет gcal_mcp_client.list_google_calendar_tools() вместо LLM.
#######################################

import asyncio
import json
import os
import sys
from datetime import datetime

from openai import OpenAI

from gcal_mcp_client import call_google_calendar_tool, list_google_calendar_tools

API_KEY = os.environ.get("DEEPSEEK_API_KEY")

if not API_KEY:
    print("Error: Please set DEEPSEEK_API_KEY environment variable")
    print("Run: export DEEPSEEK_API_KEY='your-key-here'")
    sys.exit(1)

client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.deepseek.com",
)

# Триггерные фразы, по которым вместо LLM вызывается MCP-сервер Google Calendar
GCAL_TOOLS_TRIGGERS = (
    "список инструментов google calendar",
    "google calendar tools",
    "list google calendar tools",
)

# Схема инструментов Google Calendar в формате OpenAI function-calling,
# заполняется один раз при старте через load_calendar_tools()
CALENDAR_TOOLS_SCHEMA: list = []


def load_calendar_tools() -> None:
    """Загружает реальные MCP-инструменты Google Calendar и строит function-схему для DeepSeek."""
    global CALENDAR_TOOLS_SCHEMA
    if not os.environ.get("GOOGLE_ACCESS_TOKEN"):
        print(
            "Внимание: GOOGLE_ACCESS_TOKEN не задан — вопросы про календарь "
            "будут отвечены без доступа к реальным данным.\n"
        )
        return
    try:
        tools = asyncio.run(list_google_calendar_tools())
    except Exception as exc:
        print(f"Не удалось загрузить инструменты Google Calendar: {exc}\n")
        return

    CALENDAR_TOOLS_SCHEMA = [
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


def ask_deepseek_with_calendar_tools(question: str) -> str:
    """Запрос к DeepSeek с доступом к реальным MCP-инструментам Google Calendar.

    LLM сам решает, нужно ли вызвать инструмент (например list_events), и сам
    вычисляет конкретные параметры (даты вроде "tomorrow" -> ISO 8601),
    опираясь на текущую дату из системного промпта.
    """
    now_iso = datetime.now().astimezone().isoformat()
    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful assistant with access to the user's Google Calendar "
                f"via tools. Current date and time: {now_iso}. When the user asks about "
                "their calendar, events, or schedule, call the appropriate tool with "
                "concrete ISO 8601 date/time values computed relative to the current date."
            ),
        },
        {"role": "user", "content": question},
    ]

    response = client.chat.completions.create(
        model="deepseek-v4-flash",
        messages=messages,
        tools=CALENDAR_TOOLS_SCHEMA,
        tool_choice="auto",
        max_tokens=1000,
        temperature=0.7,
    )
    message = response.choices[0].message

    if not message.tool_calls:
        return message.content

    # Модель решила вызвать один или несколько MCP-инструментов Google Calendar
    messages.append(message.model_dump(exclude_none=True))
    for tool_call in message.tool_calls:
        arguments = json.loads(tool_call.function.arguments or "{}")
        try:
            tool_result = asyncio.run(
                call_google_calendar_tool(tool_call.function.name, arguments)
            )
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
    """Обычный запрос к DeepSeek (как в test_deepseek_task_2.py)."""
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


async def handle_gcal_tools_request() -> str:
    """Вызывает MCP-сервер Google Calendar и форматирует список инструментов."""
    try:
        tools = await list_google_calendar_tools()
    except Exception as exc:
        return f"Не удалось получить список инструментов Google Calendar: {exc}"

    if not tools:
        return "Google Calendar MCP вернул пустой список инструментов."

    lines = [f"Доступно инструментов Google Calendar: {len(tools)}"]
    for tool in tools:
        lines.append(f"- {tool.name}: {tool.description or 'без описания'}")
    return "\n".join(lines)


def is_gcal_tools_request(text: str) -> bool:
    """Проверяет, просит ли пользователь список инструментов Google Calendar."""
    lowered = text.lower()
    return any(trigger in lowered for trigger in GCAL_TOOLS_TRIGGERS)


def main() -> None:
    print("Чат с агентом (DeepSeek). Для выхода введите 'exit' или 'quit'.")
    print('Подсказка: напишите "список инструментов google calendar", чтобы вызвать MCP-сервер.')
    print('Или спросите что-нибудь про календарь: "What\'s on my calendar tomorrow?"\n')

    load_calendar_tools()

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

        if is_gcal_tools_request(user_input):
            # Перехватываем запрос и обращаемся к MCP-серверу вместо LLM
            answer = asyncio.run(handle_gcal_tools_request())
        elif CALENDAR_TOOLS_SCHEMA:
            # Есть доступ к MCP-инструментам Google Calendar — даём LLM решить,
            # нужно ли вызвать list_events/search_events и с какими параметрами
            answer = ask_deepseek_with_calendar_tools(user_input)
        else:
            answer = ask_deepseek(user_input)

        print(f"Агент: {answer}\n")


if __name__ == "__main__":
    main()
