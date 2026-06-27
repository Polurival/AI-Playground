#!/usr/bin/env python3
"""
Клиент к HackerNews Digest MCP-серверу (hn_mcp_server.py).

Запускает сервер как подпроцесс и общается по stdio-транспорту.

Использование (прямой запуск для проверки):
    python3 hn_mcp_client.py
"""

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_SCRIPT = str(Path(__file__).parent / "hn_mcp_server.py")

_SERVER_PARAMS = StdioServerParameters(
    command=sys.executable,
    args=[SERVER_SCRIPT],
)


@asynccontextmanager
async def _hn_mcp_session():
    """Запускает hn_mcp_server.py как подпроцесс и открывает MCP-сессию по stdio."""
    async with stdio_client(_SERVER_PARAMS) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            yield session


async def _call_mcp(action):
    """Выполняет `action(session)` внутри MCP-сессии, оборачивает ошибки."""
    try:
        async with _hn_mcp_session() as session:
            return await action(session)
    except* Exception as eg:
        print(f"Ошибка запроса к HN MCP-серверу: {eg.exceptions}", file=sys.stderr)
        raise


async def list_hn_tools() -> list:
    """Возвращает список инструментов HN MCP-сервера."""
    response = await _call_mcp(lambda session: session.list_tools())
    return response.tools


async def call_hn_tool(tool_name: str, arguments: dict):
    """Вызывает конкретный инструмент HN MCP-сервера."""
    return await _call_mcp(lambda session: session.call_tool(tool_name, arguments))


def print_tools(tools: list) -> None:
    if not tools:
        print("Сервер не вернул ни одного инструмента.")
        return
    print(f"Доступно инструментов: {len(tools)}\n")
    for tool in tools:
        print(f"- {tool.name}")
        if tool.description:
            first_line = tool.description.strip().split("\n")[0]
            print(f"  {first_line}")
        print()


async def main() -> None:
    print("=== HN Digest MCP Client ===\n")
    tools = await list_hn_tools()
    print_tools(tools)

    print("--- Тест: collect_now ---")
    result = await call_hn_tool("collect_now", {"limit": 10})
    for item in result.content:
        print(getattr(item, "text", item))

    print("\n--- Тест: get_scheduler_status ---")
    result = await call_hn_tool("get_scheduler_status", {})
    for item in result.content:
        print(getattr(item, "text", item))

    print("\n--- Тест: get_digest ---")
    result = await call_hn_tool("get_digest", {"hours": 24, "min_score": 0})
    for item in result.content:
        print(getattr(item, "text", item))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        sys.exit(1)
