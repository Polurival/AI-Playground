#!/usr/bin/env python3
"""MCP server exposing the assistant's tools: web, workspace files, calculator, clock.

The assistant only reaches the outside world through these tools. Launched as a stdio subprocess
by `mcp_client.py` (same pattern as the week_7 file/CRM servers). Env:
  ASSISTANT_WORKSPACE  directory file tools are confined to
  ASSISTANT_READ_ONLY  "1" = write tools are not registered at all
"""

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

import file_tools
import misc_tools
import web_tools

mcp = FastMCP("assistant-mcp-server")

ROOT = os.environ.get("ASSISTANT_WORKSPACE", str(Path(__file__).parent / "workspace"))
READ_ONLY = os.environ.get("ASSISTANT_READ_ONLY") == "1"


@mcp.tool()
def web_search(query: str, max_results: int = 5) -> str:
    """Search the web (DuckDuckGo). Returns titles, URLs and snippets. Use fetch_url to read a page.

    Args:
        query: search query.
        max_results: how many results to return (1-10).
    """
    return web_tools.web_search(query, max_results)


@mcp.tool()
def fetch_url(url: str, max_chars: int = 8000) -> str:
    """Download a web page and return its readable text (truncated).

    Args:
        url: full http(s) URL.
        max_chars: max characters of text to return (500-20000).
    """
    return web_tools.fetch_url(url, max_chars)


@mcp.tool()
def list_files(glob: str = "**/*") -> str:
    """List files in the workspace (relative paths).

    Args:
        glob: glob pattern, e.g. '**/*.md'.
    """
    files = file_tools.list_files(ROOT, glob)
    return "\n".join(files) if files else "(no matching files)"


@mcp.tool()
def read_file(path: str) -> str:
    """Read a workspace file, with line numbers.

    Args:
        path: path relative to the workspace.
    """
    try:
        return file_tools.read_file(ROOT, path)
    except (FileNotFoundError, ValueError) as exc:
        return f"error: {exc}"


@mcp.tool()
def search_files(pattern: str, glob: str = "**/*") -> str:
    """Case-insensitive regex search across workspace files. Returns 'path:line: text'.

    Args:
        pattern: Python regular expression.
        glob: restrict to files matching this glob.
    """
    try:
        hits = file_tools.search_files(ROOT, pattern, glob)
    except ValueError as exc:
        return f"error: {exc}"
    return "\n".join(hits[:200]) if hits else f"(no matches for {pattern!r})"


if not READ_ONLY:
    @mcp.tool()
    def write_file(path: str, content: str, append: bool = False) -> str:
        """Create or overwrite a workspace file (parent dirs are created). Pass the FULL content,
        or set append=true to add to the end of an existing file.

        Args:
            path: path relative to the workspace.
            content: text to write.
            append: append instead of overwrite.
        """
        try:
            return file_tools.write_file(ROOT, path, content, append)
        except (ValueError, OSError) as exc:
            return f"error: {exc}"


@mcp.tool()
def calculate(expression: str) -> str:
    """Evaluate a math expression exactly (+ - * / // % **, sqrt, log, sin, round, pi, e ...).

    Args:
        expression: e.g. '2**10 + sqrt(144)'.
    """
    return misc_tools.calculate(expression)


@mcp.tool()
def current_datetime() -> str:
    """Current local date, time and weekday."""
    return misc_tools.current_datetime()


if __name__ == "__main__":
    mcp.run()
