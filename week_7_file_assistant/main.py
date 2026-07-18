#!/usr/bin/env python3
"""File-assistant CLI.

Point it at ANY project with --root; it operates on that project's files through the file MCP
server. You give it a GOAL ("update the README to describe all channels") and it decides which
files to read, search and change itself.

Usage:
    # run a goal (dry-run: changes shown as diffs, nothing written)
    python3 main.py --root sample_project do "find every usage of Notifier"

    # run a goal and actually write the changes to disk
    python3 main.py --root sample_project --apply do "add a CHANGELOG entry for recent changes"

    # list the MCP file tools (connectivity check)
    python3 main.py --root sample_project tools

    # interactive session
    python3 main.py --root sample_project
        <goal>            run a goal in the current mode
        /apply on|off     toggle write-to-disk vs dry-run
        /tools            list MCP tools
        /quit
"""

import argparse
import asyncio
import logging
import sys

import _bootstrap  # noqa: F401 — wires sys.path to week_5 llm_provider

import llm_provider

from assistant import run_goal
from config import FileAssistantConfig
from file_mcp_client import list_file_tools


def _fmt_args(args: dict) -> str:
    """Compact one-line rendering of tool args for the trace (truncate big content)."""
    parts = []
    for k, v in args.items():
        s = str(v).replace("\n", "\\n")
        if len(s) > 60:
            s = s[:57] + "..."
        parts.append(f"{k}={s}")
    return ", ".join(parts)


def _print_result(res: dict, mode: str) -> None:
    print(f"\n--- agent trace ({len(res['steps'])} tool calls, mode={mode}) ---")
    for i, step in enumerate(res["steps"], 1):
        print(f"{i}. {step['tool']}({_fmt_args(step['args'])})")

    # Surface the actual changes: every proposed/written file's unified diff.
    diffs = [s for s in res["steps"] if s["tool"] in ("propose_change", "write_file")]
    if diffs:
        heading = "Applied changes" if mode == "apply" else "Proposed changes (dry-run — nothing written)"
        print(f"\n=== {heading} ===")
        for s in diffs:
            print(f"\n# {s['args'].get('path', '?')}")
            print(str(s["observation"]).strip())

    if res.get("changed_files"):
        print(f"\nChanged files (written to disk): {', '.join(res['changed_files'])}")

    print("\n=== Result ===")
    print(res["final"].strip())
    print(f"\n[provider: {res.get('provider')} | steps: {len(res['steps'])}"
          f"{' | STOPPED at max steps' if res.get('stopped') else ''}]")


def _print_tools(cfg: FileAssistantConfig) -> None:
    tools = asyncio.run(list_file_tools(cfg.root))
    print(f"File MCP tools for '{cfg.name}' ({cfg.root}):\n")
    for t in tools:
        desc = (t.description or "").strip().splitlines()[0] if t.description else ""
        print(f"- {t.name}: {desc}")


def _repl(cfg: FileAssistantConfig, max_steps: int) -> None:
    print(f"File assistant for '{cfg.name}'  (root: {cfg.root})")
    print(f"Provider: {llm_provider.current_label()}  |  mode: {'apply' if cfg.apply else 'dry-run'}")
    print("Type a goal, or: /apply on|off  /tools  /quit\n")
    while True:
        try:
            line = input(f"{cfg.name}> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line in ("/quit", "/exit", "/q"):
            break
        if line.startswith("/apply"):
            parts = line.split()
            if len(parts) == 2 and parts[1] in ("on", "off"):
                cfg.apply = parts[1] == "on"
                print(f"mode -> {'apply' if cfg.apply else 'dry-run'}")
            else:
                print(f"current mode: {'apply' if cfg.apply else 'dry-run'} (use /apply on|off)")
            continue
        if line == "/tools":
            _print_tools(cfg)
            continue
        _print_result(run_goal(cfg, line, max_steps=max_steps), "apply" if cfg.apply else "dry-run")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Goal-driven file assistant (agent + file MCP).")
    parser.add_argument("--root", default="", help="target project path (default: ./sample_project)")
    parser.add_argument("--name", default="", help="project label (defaults to root dir name)")
    parser.add_argument("--apply", action="store_true", help="write changes to disk (default: dry-run diffs)")
    parser.add_argument("--max-steps", type=int, default=12, help="max tool calls per goal")
    parser.add_argument("-v", "--verbose", action="store_true", help="show agent/tool logs")
    sub = parser.add_subparsers(dest="command")
    p_do = sub.add_parser("do", help="run a goal-level task")
    p_do.add_argument("goal", nargs="+", help="the goal for the assistant")
    sub.add_parser("tools", help="list the file MCP tools")

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    cfg = FileAssistantConfig(root=args.root, name=args.name, apply=args.apply)

    if args.command == "tools":
        _print_tools(cfg)
        return 0
    if args.command == "do":
        res = run_goal(cfg, " ".join(args.goal), max_steps=args.max_steps)
        _print_result(res, "apply" if cfg.apply else "dry-run")
        return 0
    _repl(cfg, args.max_steps)
    return 0


if __name__ == "__main__":
    sys.exit(main())
