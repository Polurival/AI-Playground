"""Live git context for the target project, fetched over MCP.

The assistant does not shell out to git itself — it talks to the git MCP server built in
`week_4_mcp/day_17_create_mcp` (a subprocess speaking MCP over stdio) via that day's
`call_git_tool` client. This is the assignment's "connect the assistant to the project through
MCP" step: minimum = current branch; here we also expose status, tracked-file list, and diff.

`gather_context` returns a compact text block that gets folded into the /help prompt so the
assistant can answer live questions like "what branch am I on?" or "what changed?".
"""

import asyncio
import logging

import _bootstrap  # noqa: F401 — sets sys.path for the reused day_17 client

from git_mcp_client import call_git_tool

logger = logging.getLogger(__name__)


def _text(result) -> str:
    """Flatten an MCP tool result's content items into a single string."""
    parts = [getattr(item, "text", str(item)) for item in getattr(result, "content", [])]
    return "\n".join(p for p in parts if p).strip()


async def _call(tool: str, repo_path: str, **extra) -> str:
    try:
        result = await call_git_tool(tool, {"repo_path": repo_path, **extra})
        return _text(result)
    except Exception as exc:
        logger.warning("[GIT-MCP] %s failed: %s", tool, exc)
        return ""


async def _gather(repo_path: str, include_diff: bool, include_files: bool) -> dict:
    branch = await _call("git_current_branch", repo_path)
    status = await _call("git_status", repo_path)
    log = await _call("git_log", repo_path, max_count=5)
    files = await _call("git_ls_files", repo_path, pattern="docs/*") if include_files else ""
    diff = await _call("git_diff", repo_path) if include_diff else ""
    return {"branch": branch, "status": status, "log": log, "files": files, "diff": diff}


def get_git_facts(repo_path: str, include_diff: bool = False, include_files: bool = False) -> dict:
    """Synchronous entry point: run the async MCP calls and return the raw fact dict."""
    return asyncio.run(_gather(repo_path, include_diff, include_files))


def current_branch(repo_path: str) -> str:
    """Minimum-required MCP capability: the current git branch."""
    return asyncio.run(_call("git_current_branch", repo_path)) or "(unknown)"


def gather_context(repo_path: str, include_diff: bool = False, include_files: bool = False) -> str:
    """Human/LLM-readable git context block for the prompt (empty sections omitted)."""
    facts = get_git_facts(repo_path, include_diff=include_diff, include_files=include_files)
    lines = [f"Current branch: {facts['branch'] or '(unknown)'}"]
    if facts["status"]:
        lines.append(f"Working tree status:\n{facts['status']}")
    if facts["log"]:
        lines.append(f"Recent commits:\n{facts['log']}")
    if facts["files"]:
        lines.append(f"Tracked doc files:\n{facts['files']}")
    if facts["diff"]:
        diff = facts["diff"]
        if len(diff) > 4000:
            diff = diff[:4000] + "\n...(diff truncated)"
        lines.append(f"Uncommitted diff:\n{diff}")
    return "\n\n".join(lines)
