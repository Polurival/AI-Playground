"""The assistant brain: a native tool-calling loop over the MCP toolbox.

For each user message the model may call tools (web search, page fetch, files, calculator, clock)
any number of times, up to `max_steps` rounds, then answers in plain text. Conversation history is
kept across turns, so follow-ups ("and in Berlin?") work.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Callable

from openai import AsyncOpenAI

import llm
from config import AssistantConfig
from mcp_client import ToolBox

logger = logging.getLogger(__name__)

MAX_OBS_CHARS = 12_000          # cap on one tool result kept in history
MAX_HISTORY_MSGS = 40           # older turns are dropped beyond this

SYSTEM_PROMPT = """\
You are a general-purpose AI assistant. You can answer questions directly, and you have tools:
web search + page fetching, a file workspace (list/read/search{write}), a calculator and a clock.

How to work:
- Answer from your own knowledge when the question is stable and general. Use tools when the task
  needs fresh/external facts (news, prices, versions, "latest"), exact arithmetic, the current
  date/time, or the user's files.
- For web questions: web_search first, then fetch_url on the 1-3 most relevant results if snippets
  are not enough. Cite sources as URLs in the answer. Never invent facts or URLs you did not see.
- Files: all paths are relative to the workspace. Read a file before changing it.{write_rule}
- Do arithmetic with `calculate`, not in your head. Ask for the date with `current_datetime`.
- If a tool returns "error: ...", try another approach (different query/URL) or say honestly
  what you could not do.
- Be concise. Reply in {lang}, unless the user writes in another language."""

LANGS = {"ru": "Russian", "en": "English"}


def build_system_prompt(cfg: AssistantConfig) -> str:
    write = "/write" if not cfg.read_only else ""
    write_rule = ("\n- To create or change a file you MUST call write_file; never claim a file was "
                  "saved without calling it. Mention the path in your answer."
                  if not cfg.read_only else "\n- The workspace is READ-ONLY: you cannot create or modify files.")
    return SYSTEM_PROMPT.format(write=write, write_rule=write_rule, lang=LANGS.get(cfg.lang, cfg.lang))


@dataclass
class Assistant:
    cfg: AssistantConfig
    toolbox: ToolBox
    client: AsyncOpenAI
    on_step: Callable[[str, dict], None] | None = None      # trace hook: (tool, args)
    messages: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.messages = [{"role": "system", "content": build_system_prompt(self.cfg)}]

    def reset(self) -> None:
        self.messages = self.messages[:1]

    def _trim(self) -> None:
        """Drop the oldest turns (keep system prompt); never start history on a tool message."""
        while len(self.messages) > MAX_HISTORY_MSGS:
            del self.messages[1]
            while len(self.messages) > 1 and self.messages[1]["role"] != "user":
                del self.messages[1]

    async def ask(self, text: str) -> dict:
        """Process one user message. Returns {"answer", "steps": [{tool,args,observation}], "stopped"}."""
        self.messages.append({"role": "user", "content": text})
        steps: list[dict] = []
        for round_no in range(1, self.cfg.max_steps + 2):
            budget_spent = round_no > self.cfg.max_steps
            if budget_spent:        # final round: no tools offered, force a written answer
                self.messages.append({"role": "user", "content":
                    "Tool budget reached. Answer now using only what you already learned; say what is missing."})
            msg = await llm.chat(self.cfg, self.client, self.messages,
                                 None if budget_spent else self.toolbox.schemas)
            if not msg.tool_calls:
                answer = (msg.content or "").strip()
                self.messages.append({"role": "assistant", "content": answer})
                self._trim()
                return {"answer": answer, "steps": steps, "stopped": budget_spent}

            self.messages.append({
                "role": "assistant", "content": msg.content or "",
                "tool_calls": [{"id": tc.id, "type": "function",
                                "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                               for tc in msg.tool_calls]})
            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args, obs = {}, "error: tool arguments were not valid JSON"
                else:
                    if self.on_step:
                        self.on_step(name, args)
                    try:
                        obs = await self.toolbox.call(name, args)
                    except Exception as exc:                        # noqa: BLE001
                        obs = f"error running {name}: {exc}"
                logger.info("[AGENT] %s(%s) -> %d chars", name, args, len(obs))
                steps.append({"tool": name, "args": args, "observation": obs})
                self.messages.append({"role": "tool", "tool_call_id": tc.id, "content": obs[:MAX_OBS_CHARS]})
        raise AssertionError("unreachable")
