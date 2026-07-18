"""The agentic tool-loop.

`llm_provider.chat_completion` returns plain text (no native `tools`/`tool_calls`), so tool use
is driven by a text JSON protocol (ReAct style): at every step the model must answer with EXACTLY
one JSON object — either

    {"tool": "<name>", "args": {...}}     to call a tool, or
    {"final": "<report>"}                 to finish.

This loop parses that JSON, runs the tool through the supplied `call_tool` callback (which reaches
the file MCP server), feeds the result back as an observation, and asks again — until the model
emits `final` or `max_steps` is hit. Parse/tool errors are handed back to the model as
observations so it can self-correct instead of crashing the run.

Provider-agnostic by construction: it only ever calls `chat_completion`.
"""

from __future__ import annotations

import json
import logging
from typing import Callable

import _bootstrap  # noqa: F401 — wires sys.path to week_5 llm_provider

import llm_provider

logger = logging.getLogger(__name__)

WRITE_TOOLS = {"write_file"}                        # tools that mutate disk on apply
CHANGE_TOOLS = {"write_file", "propose_change"}     # tools that produce a change (diff or write)

FINAL_WITHOUT_CHANGE_NUDGE = (
    "You are about to finish, but you have not called any change tool (propose_change/write_file). "
    "If the goal requires creating or modifying a file, call the change tool NOW with the file's "
    "FULL new content so the change actually happens. If the goal is read-only (search/analyze), "
    "reply with your {\"final\": ...} again."
)


def _extract_json(text: str) -> dict | None:
    """Best-effort parse of a single JSON object out of the model's reply.

    Handles ```json fences and leading/trailing prose by scanning for the first balanced { }.
    """
    if not text:
        return None
    s = text.strip()
    # Strip only an OUTER wrapping fence (```json ... ```). Do NOT regex for any fence: the JSON
    # string value can itself contain ```python code blocks (e.g. when writing a README), and a
    # greedy fence match would cut the content at the first inner ``` and corrupt the JSON.
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    # find the first balanced brace span
    start = s.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = s[start:i + 1]
                try:
                    # strict=False tolerates literal control chars (newlines/tabs) inside
                    # strings — models routinely emit multi-line file content as a raw JSON
                    # string value rather than escaping every "\n", which strict JSON rejects.
                    return json.loads(candidate, strict=False)
                except json.JSONDecodeError:
                    return None
    return None


def run(
    system_prompt: str,
    goal: str,
    call_tool: Callable[[str, dict], str],
    max_steps: int = 8,
    max_tokens: int = 1500,
) -> dict:
    """Drive the tool-loop for one goal.

    Returns {"final", "steps": [{tool,args,observation}], "changed_files": [...], "stopped": bool}.
    `stopped` is True when max_steps was hit before the model finished.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Goal: {goal}\n\nRespond with one JSON object as instructed."},
    ]
    steps: list[dict] = []
    changed: list[str] = []
    change_calls = 0
    nudged = False

    for step in range(1, max_steps + 1):
        raw = llm_provider.chat_completion(messages, max_tokens=max_tokens, temperature=0.0)
        parsed = _extract_json(raw)

        if parsed is None:
            logger.warning("[AGENT] step %d: unparseable reply, asking model to retry", step)
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content":
                "That was not a single valid JSON object. Reply with EXACTLY one JSON object: "
                '{"tool": "...", "args": {...}} or {"final": "..."}.'})
            continue

        if "final" in parsed:
            # Guardrail: if it finalizes having made no change at all, nudge once — this catches
            # the model "claiming" it updated a file without ever calling a change tool.
            if change_calls == 0 and not nudged:
                nudged = True
                logger.info("[AGENT] final without any change tool — nudging once")
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content": FINAL_WITHOUT_CHANGE_NUDGE})
                continue
            return {"final": str(parsed["final"]), "steps": steps,
                    "changed_files": changed, "stopped": False}

        tool = parsed.get("tool")
        args = parsed.get("args") or {}
        if not tool:
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content":
                'Missing "tool" or "final" key. Reply with one valid JSON object.'})
            continue

        logger.info("[AGENT] step %d: tool=%s args=%s", step, tool, args)
        try:
            observation = call_tool(tool, args)
        except Exception as exc:                                   # noqa: BLE001
            observation = f"error running tool {tool}: {exc}"
        if tool in CHANGE_TOOLS and not str(observation).startswith("error"):
            change_calls += 1
        if tool in WRITE_TOOLS and not str(observation).startswith("error") and args.get("path"):
            if args["path"] not in changed:
                changed.append(args["path"])

        steps.append({"tool": tool, "args": args, "observation": observation})
        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user", "content": f"Observation from {tool}:\n{observation}"})

    logger.warning("[AGENT] hit max_steps=%d without a final answer", max_steps)
    return {"final": "(stopped: reached max steps without finishing)",
            "steps": steps, "changed_files": changed, "stopped": True}
