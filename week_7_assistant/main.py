#!/usr/bin/env python3
"""Developer-assistant CLI.

Point it at ANY git repo with docs — the pipeline is project-agnostic (repo path + doc globs are
config, not hardcoded).

Usage:
    # 1) index the project's docs into a per-project vector store (run once, or after doc changes)
    python3 main.py --repo /path/to/project ingest

    # 2a) ask a single question
    python3 main.py --repo /path/to/project help "How do I define an optional CLI argument?"

    # 2b) interactive session — the /help command answers questions about the project
    python3 main.py --repo /path/to/project
        /help how do I create a subcommand?
        /branch                 # current git branch, live via MCP
        /model local|deepseek   # switch LLM backend
        /quit
"""

import argparse
import logging
import sys

import _bootstrap  # noqa: F401 — sets sys.path for the reused week_5/week_4 modules

import llm_provider

from config import ProjectConfig
from ingest import ingest_project
from assistant import answer_help
import git_context


def _print_result(res: dict) -> None:
    print("\n" + res["answer"].strip() + "\n")
    if res.get("sources"):
        print("Sources:")
        for s in res["sources"]:
            rr = s.get("rerank_score")
            rr_txt = f", rerank={rr:.3f}" if rr is not None else ""
            print(f"  - {s['meta_file']} :: {s['meta_section']} (cosine={s['score']:.3f}{rr_txt})")
    print(f"\n[provider: {res.get('provider')} | rewritten: {res.get('rewritten_query')!r} | "
          f"max_cosine: {res.get('max_score', 0.0):.3f}]")


def _repl(cfg: ProjectConfig) -> None:
    print(f"Developer assistant for '{cfg.name}'  (docs: {cfg.db_path})")
    print(f"Provider: {llm_provider.current_label()}  |  available: {llm_provider.available_providers()}")
    print("Commands: /help <question>  /branch  /diff  /model <local|deepseek>  /quit\n")
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
        if line.startswith("/model"):
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                try:
                    print("switched ->", llm_provider.set_provider(parts[1]))
                except ValueError as exc:
                    print("error:", exc)
            else:
                print("current:", llm_provider.current_label())
            continue
        if line == "/branch":
            print("branch:", git_context.current_branch(cfg.repo_path))
            continue
        if line == "/diff":
            print(git_context.gather_context(cfg.repo_path, include_diff=True) or "(no context)")
            continue
        if line.startswith("/help"):
            q = line[len("/help"):].strip()
            if not q:
                print("usage: /help <your question about the project>")
                continue
            _print_result(answer_help(cfg, q))
            continue
        # bare text is treated as a /help question too, for convenience
        _print_result(answer_help(cfg, line))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RAG + MCP developer assistant (project-agnostic).")
    parser.add_argument("--repo", required=True, help="path to the target git repository")
    parser.add_argument("--name", default="", help="project label (defaults to repo dir name)")
    parser.add_argument("--db", default="", help="override the sqlite index path")
    parser.add_argument("-v", "--verbose", action="store_true", help="show pipeline logs")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("ingest", help="index the project's docs into the vector store")
    p_help = sub.add_parser("help", help="answer a single question")
    p_help.add_argument("question", nargs="+", help="the question to answer")

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    cfg = ProjectConfig(repo_path=args.repo, name=args.name, db_path=args.db)

    if args.command == "ingest":
        n = ingest_project(cfg)
        print(f"Ingested {n} chunks from '{cfg.name}' -> {cfg.db_path}")
        return 0
    if args.command == "help":
        _print_result(answer_help(cfg, " ".join(args.question)))
        return 0
    _repl(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
