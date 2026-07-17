#!/usr/bin/env python3
"""
Клиент к собственному MCP-серверу CRM (crm_mcp_server.py).

Сервер локальный, поэтому клиент запускает его подпроцессом и общается по stdio-транспорту MCP —
та же схема, что в week_4_mcp/day_17_create_mcp/git_mcp_client.py.

Проверка вручную (печатает список инструментов и карточку тикета TCK-1042):
    python3 crm_mcp_client.py
"""

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_SCRIPT = str(Path(__file__).parent / "crm_mcp_server.py")


def _server_params(crm_data_dir: str = "") -> StdioServerParameters:
    """Параметры запуска сервера; каталог данных CRM передаётся через окружение."""
    env = dict(os.environ)
    if crm_data_dir:
        env["CRM_DATA_DIR"] = crm_data_dir
    return StdioServerParameters(command=sys.executable, args=[SERVER_SCRIPT], env=env)


@asynccontextmanager
async def _crm_mcp_session(crm_data_dir: str = ""):
    """Запускает crm_mcp_server.py как подпроцесс и открывает MCP-сессию по stdio."""
    async with stdio_client(_server_params(crm_data_dir)) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            # Обязательный handshake перед любыми запросами
            await session.initialize()
            yield session


async def _call_mcp(action, crm_data_dir: str = ""):
    """Выполняет `action(session)` внутри MCP-сессии, оборачивая ошибки."""
    try:
        async with _crm_mcp_session(crm_data_dir) as session:
            return await action(session)
    except* Exception as eg:
        print(f"Ошибка запроса к CRM MCP-серверу: {eg.exceptions}", file=sys.stderr)
        raise


async def list_crm_tools(crm_data_dir: str = "") -> list:
    """Подключается к CRM MCP-серверу и возвращает список инструментов."""
    response = await _call_mcp(lambda session: session.list_tools(), crm_data_dir)
    return response.tools


async def call_crm_tool(tool_name: str, arguments: dict, crm_data_dir: str = ""):
    """Вызывает конкретный инструмент CRM MCP-сервера (например crm_get_ticket)."""
    return await _call_mcp(lambda session: session.call_tool(tool_name, arguments), crm_data_dir)


def print_tools(tools: list) -> None:
    """Печатает структуру инструментов в консоль в читаемом виде."""
    if not tools:
        print("Сервер не вернул ни одного инструмента.")
        return
    print(f"Доступно инструментов: {len(tools)}\n")
    for tool in tools:
        print(f"- {tool.name}")
        if tool.description:
            print(f"  description: {tool.description.strip().splitlines()[0]}")
    print()


async def main() -> None:
    tools = await list_crm_tools()
    print_tools(tools)

    result = await call_crm_tool("crm_get_ticket", {"ticket_id": "TCK-1042"})
    print("Пример вызова crm_get_ticket:\n")
    for item in result.content:
        print(getattr(item, "text", item))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        sys.exit(1)
