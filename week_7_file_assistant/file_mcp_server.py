#!/usr/bin/env python3
"""MCP server exposing the project's files as tools.

The assistant never opens files directly — it goes through these tools, exactly as it would talk
to a real filesystem service over MCP. Built on the same pattern as
`week_4_mcp/day_17_create_mcp/git_mcp_server.py` and the week_7 CRM server: FastMCP raises a
stdio server on launch, and `file_mcp_client.py` starts it as a subprocess.

The project root is taken from the FILE_ASSISTANT_ROOT environment variable (passed in by the
client). Every path argument is relative to that root; `file_tools._safe_path` refuses anything
that escapes it.

Two write-side tools split by intent:
  - `propose_change` always returns a unified diff and NEVER touches disk (dry-run);
  - `write_file` actually writes.
The assistant is told (via its system prompt) which one to use based on the run's apply/dry-run
mode, so the server itself stays a dumb, honest filesystem.
"""

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

import file_tools

mcp = FastMCP("file-mcp-server")

ROOT = os.environ.get("FILE_ASSISTANT_ROOT", str(Path(__file__).parent / "sample_project"))


@mcp.tool()
def list_files(glob: str = "") -> str:
    """List project files (relative paths). Optionally restrict to a single glob, e.g. '**/*.py'.

    Args:
        glob: a single glob pattern; empty means the default code+docs set.
    """
    globs = [glob] if glob else None
    files = file_tools.list_files(ROOT, globs)
    return "\n".join(files) if files else "(no matching files)"


@mcp.tool()
def read_file(path: str) -> str:
    """Read one project file, returned with line numbers (so you can cite file:line).

    Args:
        path: file path relative to the project root.
    """
    try:
        return file_tools.read_file(ROOT, path)
    except (FileNotFoundError, ValueError) as exc:
        return f"error: {exc}"


@mcp.tool()
def search_files(pattern: str, glob: str = "", ignore_case: bool = False) -> str:
    """Regex-search across many files at once. Returns 'path:line: text' matches.

    Args:
        pattern: a Python regular expression.
        glob: restrict the search to this glob (empty = default code+docs set).
        ignore_case: case-insensitive match when true.
    """
    globs = [glob] if glob else None
    try:
        hits = file_tools.search_files(ROOT, pattern, globs, ignore_case)
    except ValueError as exc:
        return f"error: {exc}"
    if not hits:
        return f"(no matches for {pattern!r})"
    return "\n".join(f"{h['path']}:{h['line']}: {h['text']}" for h in hits)


@mcp.tool()
def analyze_project() -> str:
    """Summarize the project: file count, files per extension, total lines, entry points."""
    a = file_tools.analyze_project(ROOT)
    lines = [
        f"root: {a['root']}",
        f"files: {a['file_count']}",
        f"total lines: {a['total_lines']}",
        "by extension: " + ", ".join(f"{k}={v}" for k, v in a["by_extension"].items()),
        "entry points: " + (", ".join(a["entry_points"]) or "(none)"),
        "file list:",
        *[f"  {f}" for f in a["files"]],
    ]
    return "\n".join(lines)


@mcp.tool()
def propose_change(path: str, content: str) -> str:
    """Preview a change as a unified diff WITHOUT writing to disk (dry-run mode).

    Args:
        path: file path relative to the project root.
        content: the full proposed new content of the file.
    """
    try:
        return file_tools.unified_diff(ROOT, path, content)
    except ValueError as exc:
        return f"error: {exc}"


@mcp.tool()
def write_file(path: str, content: str) -> str:
    """Create or overwrite a file on disk (apply mode). Returns a short status line.

    Args:
        path: file path relative to the project root.
        content: the full new content of the file.
    """
    try:
        diff = file_tools.unified_diff(ROOT, path, content)
        status = file_tools.write_file(ROOT, path, content)
        return f"{status}\n{diff}"
    except (ValueError, OSError) as exc:
        return f"error: {exc}"


if __name__ == "__main__":
    mcp.run()
