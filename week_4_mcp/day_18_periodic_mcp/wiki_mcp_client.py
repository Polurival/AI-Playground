#!/usr/bin/env python3
"""
Клиент к Wikipedia MCP-серверу (wiki_mcp_server.py).

Запускает сервер как подпроцесс и общается по stdio-транспорту.

Использование (прямой запуск для проверки):
    python3 wiki_mcp_client.py
"""

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_SCRIPT = str(Path(__file__).parent / "wiki_mcp_server.py")

_SERVER_PARAMS = StdioServerParameters(
    command=sys.executable,
    args=[SERVER_SCRIPT],
)


@asynccontextmanager
async def _wiki_mcp_session():
    """Запускает wiki_mcp_server.py как подпроцесс и открывает MCP-сессию по stdio."""
    async with stdio_client(_SERVER_PARAMS) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            yield session


async def _call_mcp(action):
    try:
        async with _wiki_mcp_session() as session:
            return await action(session)
    except* Exception as eg:
        print(f"Ошибка запроса к Wikipedia MCP-серверу: {eg.exceptions}", file=sys.stderr)
        raise


async def list_wiki_tools() -> list:
    """Возвращает список инструментов Wikipedia MCP-сервера."""
    response = await _call_mcp(lambda session: session.list_tools())
    return response.tools


async def call_wiki_tool(tool_name: str, arguments: dict):
    """Вызывает конкретный инструмент Wikipedia MCP-сервера."""
    return await _call_mcp(lambda session: session.call_tool(tool_name, arguments))


async def main() -> None:
    print("=== Wikipedia MCP Client ===\n")
    tools = await list_wiki_tools()
    print(f"Доступно инструментов: {len(tools)}\n")
    for tool in tools:
        print(f"- {tool.name}")
        if tool.description:
            print(f"  {tool.description.strip().splitlines()[0]}")
        print()

    print("--- Тест: search_wikipedia ---")
    result = await call_wiki_tool("search_wikipedia", {"query": "large language model", "limit": 3})
    for item in result.content:
        print(getattr(item, "text", item))

    print("\n--- Тест: get_article_summary ---")
    result = await call_wiki_tool("get_article_summary", {"title": "Large language model"})
    for item in result.content:
        text = getattr(item, "text", str(item))
        print(text[:500] + "..." if len(text) > 500 else text)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        sys.exit(1)
