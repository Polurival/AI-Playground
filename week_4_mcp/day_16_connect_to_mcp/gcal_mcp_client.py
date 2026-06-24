#!/usr/bin/env python3
"""
Скрипт подключается к удалённому официальному MCP-серверу Google Calendar
по протоколу SSE и запрашивает список доступных инструментов (list_tools).

Использование:
    export GOOGLE_ACCESS_TOKEN='ya29....'
    python3 gcal_mcp_client.py
"""

import asyncio
import os
import sys
from contextlib import asynccontextmanager

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

# Эндпоинт официального MCP-сервера Google Calendar
GCAL_MCP_URL = "https://calendarmcp.googleapis.com/mcp/v1"


@asynccontextmanager
async def _gcal_session():
    """Открывает Streamable HTTP соединение и MCP-сессию с Google Calendar."""

    # Шаг 1. Берём OAuth access token из переменных окружения.
    # Токен должен быть выпущен с нужными Calendar-скоупами.
    access_token = os.environ.get("GOOGLE_ACCESS_TOKEN")
    if not access_token:
        raise RuntimeError(
            "Не задана переменная окружения GOOGLE_ACCESS_TOKEN. "
            "Выполните: export GOOGLE_ACCESS_TOKEN='ваш_access_token'"
        )

    # Шаг 2. Авторизация передаётся через Bearer-токен в заголовке запроса.
    headers = {"Authorization": f"Bearer {access_token}"}

    # Шаг 3. Открываем Streamable HTTP соединение с MCP-сервером.
    # Сервер calendarmcp.googleapis.com отдаёт 405 на GET (классический
    # SSE-транспорт с двумя эндпоинтами) и принимает только POST —
    # это современный Streamable HTTP транспорт MCP, а не legacy SSE.
    async with streamablehttp_client(url=GCAL_MCP_URL, headers=headers) as (
        read_stream,
        write_stream,
        _get_session_id,
    ):
        # Шаг 4. Создаём MCP-сессию поверх потоков чтения/записи.
        async with ClientSession(read_stream, write_stream) as session:
            # Шаг 5. Обязательный handshake с сервером перед любыми запросами.
            await session.initialize()
            yield session


async def _call_mcp(action):
    """Выполняет `action(session)` внутри MCP-сессии, оборачивая сетевые ошибки."""
    try:
        async with _gcal_session() as session:
            return await action(session)
    except* ConnectionError as eg:
        # Сетевые проблемы при установке соединения (DNS, отказ соединения и т.д.)
        print(f"Ошибка соединения с MCP-сервером: {eg.exceptions}", file=sys.stderr)
        raise
    except* TimeoutError as eg:
        print(f"Таймаут при запросе к MCP-серверу: {eg.exceptions}", file=sys.stderr)
        raise
    except* Exception as eg:
        # Любые прочие ошибки (например, 401 при невалидном токене, ошибки протокола)
        print(f"Ошибка запроса к MCP-серверу: {eg.exceptions}", file=sys.stderr)
        raise


async def list_google_calendar_tools() -> list:
    """Подключается к MCP-серверу Google Calendar и возвращает список инструментов."""
    response = await _call_mcp(lambda session: session.list_tools())
    return response.tools


async def call_google_calendar_tool(tool_name: str, arguments: dict):
    """Вызывает конкретный инструмент MCP-сервера Google Calendar (например list_events)."""
    return await _call_mcp(lambda session: session.call_tool(tool_name, arguments))


def print_tools(tools: list) -> None:
    """Печатает структуру инструментов в консоль в читаемом виде."""
    if not tools:
        print("Сервер не вернул ни одного инструмента.")
        return

    print(f"Доступно инструментов: {len(tools)}\n")
    for tool in tools:
        print(f"- {tool.name}")
        if tool.description:
            print(f"  description: {tool.description}")
        if tool.inputSchema:
            print(f"  inputSchema: {tool.inputSchema}")
        print()


async def main() -> None:
    tools = await list_google_calendar_tools()
    print_tools(tools)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        sys.exit(1)
