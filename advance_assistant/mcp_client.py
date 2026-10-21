"""Client for the assistant MCP server: one persistent stdio session per run, plus conversion of
MCP tool definitions into OpenAI function-calling schemas (so tools are discovered, not hardcoded)."""

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from config import AssistantConfig

SERVER_SCRIPT = str(Path(__file__).parent / "mcp_server.py")


class ToolBox:
    """Live MCP session + the tool catalogue in OpenAI format."""

    def __init__(self, session: ClientSession, tools: list) -> None:
        self._session = session
        self.schemas = [{"type": "function", "function": {
            "name": t.name, "description": (t.description or "").strip(),
            "parameters": t.inputSchema}} for t in tools]
        self.names = [t.name for t in tools]

    async def call(self, name: str, args: dict) -> str:
        if name not in self.names:
            return f"error: unknown tool {name!r}. Available: {', '.join(self.names)}"
        result = await self._session.call_tool(name, args)
        text = "\n".join(getattr(c, "text", str(c)) for c in result.content).strip()
        return f"error: {text}" if result.isError and not text.startswith("error") else text


@asynccontextmanager
async def open_toolbox(cfg: AssistantConfig):
    env = dict(os.environ)
    env["ASSISTANT_WORKSPACE"] = cfg.workspace
    env["ASSISTANT_READ_ONLY"] = "1" if cfg.read_only else "0"
    params = StdioServerParameters(command=sys.executable, args=[SERVER_SCRIPT], env=env)
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()
            yield ToolBox(session, (await session.list_tools()).tools)
