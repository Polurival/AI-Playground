#!/usr/bin/env python3
"""
Клиент к собственному MCP-серверу git_mcp_server.py.

В отличие от day_16 (удалённый сервер Google Calendar по Streamable HTTP),
здесь сервер свой и локальный — клиент запускает его как подпроцесс
и общается по stdio-транспорту MCP.

Использование:
    python3 git_mcp_client.py
"""

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_SCRIPT = str(Path(__file__).parent / "git_mcp_server.py")

_SERVER_PARAMS = StdioServerParameters(
    command=sys.executable,
    args=[SERVER_SCRIPT],
)


@asynccontextmanager
async def _git_mcp_session():
    """Запускает git_mcp_server.py как подпроцесс и открывает MCP-сессию по stdio."""
    async with stdio_client(_SERVER_PARAMS) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            # Обязательный handshake перед любыми запросами
            await session.initialize()
            yield session


async def _call_mcp(action):
    """Выполняет `action(session)` внутри MCP-сессии, оборачивая ошибки."""
    try:
        async with _git_mcp_session() as session:
            return await action(session)
    except* Exception as eg:
        print(f"Ошибка запроса к git MCP-серверу: {eg.exceptions}", file=sys.stderr)
        raise


async def list_git_tools() -> list:
    """Подключается к git MCP-серверу и возвращает список инструментов."""
    response = await _call_mcp(lambda session: session.list_tools())
    return response.tools


async def call_git_tool(tool_name: str, arguments: dict):
    """Вызывает конкретный инструмент git MCP-сервера (например git_status)."""
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
    tools = await list_git_tools()
    print_tools(tools)

    # Пример реального вызова инструмента на текущем репозитории
    repo_path = str(Path(__file__).resolve().parents[2])
    result = await call_git_tool("git_log", {"repo_path": repo_path, "max_count": 5})
    print("Пример вызова git_log:\n")
    for item in result.content:
        print(getattr(item, "text", item))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        sys.exit(1)
