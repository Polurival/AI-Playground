#!/usr/bin/env python3
"""Client to the file MCP server (file_mcp_server.py).

The server is local, so this client launches it as a subprocess and speaks stdio MCP — the same
scheme as week_4_mcp/day_17_create_mcp/git_mcp_client.py and the week_7 CRM client. The project
root the server should operate on is passed through the FILE_ASSISTANT_ROOT env var.

Manual check (prints the tool list and a Notifier search on the bundled stand):
    python3 file_mcp_client.py
"""

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_SCRIPT = str(Path(__file__).parent / "file_mcp_server.py")


def _server_params(root: str = "") -> StdioServerParameters:
    """Server launch params; the project root is passed through the environment."""
    env = dict(os.environ)
    if root:
        env["FILE_ASSISTANT_ROOT"] = os.path.abspath(root)
    return StdioServerParameters(command=sys.executable, args=[SERVER_SCRIPT], env=env)


@asynccontextmanager
async def _file_mcp_session(root: str = ""):
    """Launch file_mcp_server.py as a subprocess and open a stdio MCP session."""
    async with stdio_client(_server_params(root)) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()      # mandatory handshake before any request
            yield session


async def _call_mcp(action, root: str = ""):
    try:
        async with _file_mcp_session(root) as session:
            return await action(session)
    except* Exception as eg:
        print(f"file MCP server request failed: {eg.exceptions}", file=sys.stderr)
        raise


async def list_file_tools(root: str = "") -> list:
    """Connect to the file MCP server and return its tool list."""
    response = await _call_mcp(lambda s: s.list_tools(), root)
    return response.tools


async def call_file_tool(tool_name: str, arguments: dict, root: str = ""):
    """Call one tool on the file MCP server (e.g. search_files)."""
    return await _call_mcp(lambda s: s.call_tool(tool_name, arguments), root)


def print_tools(tools: list) -> None:
    if not tools:
        print("Server returned no tools.")
        return
    print(f"Tools available: {len(tools)}\n")
    for tool in tools:
        print(f"- {tool.name}")
        if tool.description:
            print(f"  {tool.description.strip().splitlines()[0]}")
    print()


async def main() -> None:
    root = str(Path(__file__).parent / "sample_project")
    tools = await list_file_tools(root)
    print_tools(tools)

    result = await call_file_tool("search_files", {"pattern": "Notifier"}, root)
    print("Example search_files('Notifier'):\n")
    for item in result.content:
        print(getattr(item, "text", item))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        sys.exit(1)
