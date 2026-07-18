"""The file-assistant brain: turn a goal-level task into real file operations.

The user states a goal ("update the CHANGELOG from recent code changes"), not a file to open.
This module builds the system prompt (tool catalogue + strict JSON protocol + apply/dry-run
mode), then hands control to `agent_loop.run`, which lets the LLM decide which files to read,
search, analyze and write — every file touch going through the file MCP server.

LLM calls go through week_5's `llm_provider`; for this assignment the active provider is DeepSeek.
"""

from __future__ import annotations

import asyncio
import logging

import _bootstrap  # noqa: F401 — wires sys.path to week_5 llm_provider

import llm_provider

import agent_loop
from config import FileAssistantConfig
from file_mcp_client import call_file_tool

logger = logging.getLogger(__name__)

# Tool catalogue advertised to the model. Kept in sync with file_mcp_server.py.
_READ_TOOLS = """\
- list_files(glob="")            -> list project files (optional single glob, e.g. "**/*.py")
- read_file(path)                -> file content WITH line numbers (cite file:line)
- read_files(paths)              -> read MANY files at once (list of paths); prefer over many read_file calls
- search_files(pattern, glob="", ignore_case=false) -> regex grep across files: "path:line: text"
- analyze_project()              -> file count, per-extension counts, total lines, entry points"""

_WRITE_APPLY = '- write_file(path, content)      -> create/overwrite the file ON DISK, returns status + diff'
_WRITE_DRY = '- propose_change(path, content)  -> show a unified diff of the change, WITHOUT writing'

SYSTEM_PROMPT_TEMPLATE = """\
You are a file assistant that operates directly on the files of the project named "{name}".
You accomplish a GOAL by choosing and calling tools yourself — decide which files to read,
search, analyze, and change. Never ask the user to open files for you.

You interact ONLY by emitting tool calls. At EVERY step respond with EXACTLY ONE JSON object,
nothing else — no prose, no markdown, no code fences. Either call a tool:
    {{"tool": "<name>", "args": {{...}}}}
or finish with a final report:
    {{"final": "<your report in Russian>"}}

Available tools:
{read_tools}
{write_tool}

Rules:
- Explore before you conclude: list/search/read the relevant files instead of guessing.
- When you need to inspect several files, call read_files(paths=[...]) ONCE instead of read_file
  per file — it is far cheaper on your step budget.
- Cite evidence as file:line (line numbers come from read_file / search_files).
- Mode is {mode}. {mode_rule}
- When you write a file, pass its FULL new content (not a patch), preserving unrelated lines.
- To CHANGE a file you MUST actually call the change tool for it. NEVER claim in your final
  report that a file was changed unless you called the change tool and saw its diff first.
- Keep going until the goal is done, then emit {{"final": ...}} summarizing what you found or
  changed (list changed files and cite file:line). Write the final report in Russian.
- Do at most {max_steps} tool calls; be efficient."""

MODE_RULES = {
    "apply": "You MAY modify files using write_file. Changes are saved to disk.",
    "dry-run": ("You MUST NOT use write_file. To change a file, call propose_change to show its "
                "diff only — nothing is written to disk in this mode."),
}


def build_system_prompt(cfg: FileAssistantConfig, max_steps: int) -> str:
    mode = "apply" if cfg.apply else "dry-run"
    write_tool = _WRITE_APPLY if cfg.apply else _WRITE_DRY
    return SYSTEM_PROMPT_TEMPLATE.format(
        name=cfg.name,
        read_tools=_READ_TOOLS,
        write_tool=write_tool,
        mode=mode,
        mode_rule=MODE_RULES[mode],
        max_steps=max_steps,
    )


def _flatten(result) -> str:
    """Flatten an MCP tool result's content items into one string."""
    parts = [getattr(item, "text", str(item)) for item in getattr(result, "content", [])]
    return "\n".join(p for p in parts if p).strip()


def _make_call_tool(cfg: FileAssistantConfig):
    """Return a synchronous call_tool(name, args) bound to this project's MCP server.

    In dry-run mode, write_file is blocked at this layer too (defence in depth): even if the model
    ignores the prompt, the write is redirected to a diff-only preview and nothing hits disk.
    """
    def call_tool(name: str, args: dict) -> str:
        if not cfg.apply and name == "write_file":
            name = "propose_change"
        try:
            result = asyncio.run(call_file_tool(name, args, cfg.root))
        except Exception as exc:                                  # noqa: BLE001
            return f"error: MCP call {name} failed: {exc}"
        return _flatten(result)

    return call_tool


def run_goal(cfg: FileAssistantConfig, goal: str, max_steps: int = 12) -> dict:
    """Execute one goal-level task. Returns the agent_loop result dict plus the provider label."""
    system_prompt = build_system_prompt(cfg, max_steps)
    result = agent_loop.run(system_prompt, goal, _make_call_tool(cfg), max_steps=max_steps)
    result["provider"] = llm_provider.current_label()
    return result
