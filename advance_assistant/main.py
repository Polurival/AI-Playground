#!/usr/bin/env python3
"""General AI assistant CLI.

Usage:
    python3 main.py ask "what is the latest stable Python version?"   # one-shot
    python3 main.py                                                    # interactive chat
    python3 main.py --workspace ~/notes --read-only ask "summarize my notes"
    python3 main.py tools                                              # list MCP tools

Chat commands: /tools  /reset  /trace on|off  /quit
"""

import argparse
import asyncio
import logging
import sys

from agent import Assistant
from config import AssistantConfig
from llm import make_client
from mcp_client import open_toolbox


def _fmt_args(args: dict) -> str:
    parts = []
    for k, v in args.items():
        s = str(v).replace("\n", "\\n")
        parts.append(f"{k}={s[:57] + '...' if len(s) > 60 else s}")
    return ", ".join(parts)


async def _ask_once(bot: Assistant, text: str, trace: bool) -> None:
    bot.on_step = (lambda t, a: print(f"  ⚙ {t}({_fmt_args(a)})", flush=True)) if trace else None
    res = await bot.ask(text)
    print(f"\n{res['answer']}\n")
    if res["stopped"]:
        print("[tool budget exhausted — answer may be partial; raise --max-steps]\n")


async def _repl(bot: Assistant, cfg: AssistantConfig) -> None:
    trace = True
    print(f"Assistant ({cfg.llm_model})  workspace: {cfg.workspace}"
          f"{'  [read-only]' if cfg.read_only else ''}")
    print("Ask anything. Commands: /tools  /reset  /trace on|off  /quit\n")
    loop = asyncio.get_running_loop()
    while True:
        try:
            line = (await loop.run_in_executor(None, input, "you> ")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not line:
            continue
        if line in ("/quit", "/exit", "/q"):
            return
        if line == "/reset":
            bot.reset()
            print("history cleared\n")
        elif line == "/tools":
            print(", ".join(bot.toolbox.names) + "\n")
        elif line.startswith("/trace"):
            trace = line.split()[-1] != "off"
            print(f"trace {'on' if trace else 'off'}\n")
        else:
            try:
                await _ask_once(bot, line, trace)
            except RuntimeError as exc:
                print(f"error: {exc}\n")


async def amain(args) -> int:
    cfg = AssistantConfig(workspace=args.workspace, read_only=args.read_only,
                          max_steps=args.max_steps, lang=args.lang)
    async with open_toolbox(cfg) as toolbox:
        if args.command == "tools":
            for s in toolbox.schemas:
                f = s["function"]
                print(f"- {f['name']}: {f['description'].splitlines()[0]}")
            return 0
        bot = Assistant(cfg, toolbox, make_client(cfg))
        if args.command == "ask":
            await _ask_once(bot, " ".join(args.question), trace=not args.quiet)
        else:
            await _repl(bot, cfg)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="General assistant: answers, web search, files (MCP tools).")
    p.add_argument("--workspace", default="", help="directory for file tools (default: ./workspace)")
    p.add_argument("--read-only", action="store_true", help="forbid creating/modifying files")
    p.add_argument("--max-steps", type=int, default=10, help="max tool-call rounds per message")
    p.add_argument("--lang", default="ru", help="reply language: ru | en")
    p.add_argument("-v", "--verbose", action="store_true", help="show agent logs")
    sub = p.add_subparsers(dest="command")
    pa = sub.add_parser("ask", help="one-shot question")
    pa.add_argument("question", nargs="+")
    pa.add_argument("-q", "--quiet", action="store_true", help="hide tool trace")
    sub.add_parser("tools", help="list MCP tools")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    try:
        return asyncio.run(amain(args))
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
