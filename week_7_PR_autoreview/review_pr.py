"""CLI entry point for the PR auto-reviewer.

Examples
--------
Review the diff between two refs of a repo (what the GitHub Action does):

    python review_pr.py --repo /path/to/repo --base origin/main --head HEAD --out review.md

Review a pre-computed diff file (or piped via stdin):

    git diff main...HEAD | python review_pr.py --repo . --diff-file -

The script (1) builds the RAG index over the repo's docs + code, (2) computes/reads the diff,
(3) generates the review, and (4) writes Markdown to --out (and stdout).
"""

import argparse
import logging
import os
import subprocess
import sys

from config import ReviewConfig
from index import build_index
import store
from reviewer import review_diff

MARKER = "<!-- ai-autoreview -->"


def _get_diff(args) -> str:
    if args.diff_file:
        if args.diff_file == "-":
            return sys.stdin.read()
        with open(args.diff_file, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    if not (args.base and args.head):
        raise SystemExit("Provide either --diff-file or both --base and --head.")
    # Three-dot: changes on head since the merge-base with base (the PR's own changes).
    cmd = ["git", "-C", args.repo, "diff", f"{args.base}...{args.head}"]
    logging.info("[DIFF] %s", " ".join(cmd))
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"git diff failed: {out.stderr.strip()}")
    return out.stdout


def _render(result: dict, cfg: ReviewConfig) -> str:
    lines = [MARKER, f"# 🤖 AI-ревью PR — {cfg.name}", ""]
    lines.append(result["review"] or "_(пустой ответ модели)_")
    lines.append("")
    if result["files"]:
        lines.append(f"<sub>Отревьюено файлов: {len(result['files'])} · "
                     f"модель: `{cfg.llm_model}` · эмбеддинги: `{cfg.embed_model}`</sub>")
    if result["sources"]:
        srcs = ", ".join(f"`{s['file']}`" for s in result["sources"][:8])
        lines.append("")
        lines.append(f"<sub>Контекст RAG из: {srcs}</sub>")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="AI code review for a pull request (RAG over docs + code).")
    ap.add_argument("--repo", default=os.getcwd(), help="path to the repo to review (default: cwd)")
    ap.add_argument("--base", help="base ref/sha (e.g. origin/main)")
    ap.add_argument("--head", default="HEAD", help="head ref/sha (default: HEAD)")
    ap.add_argument("--diff-file", help="read the unified diff from this file ('-' for stdin) instead of git")
    ap.add_argument("--out", default="review.md", help="write the review markdown here (default: review.md)")
    ap.add_argument("--lang", help="review language: ru (default) or en")
    ap.add_argument("--no-index", action="store_true", help="reuse an existing index instead of rebuilding")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    cfg = ReviewConfig(repo_path=args.repo)
    if args.lang:
        cfg.review_lang = args.lang

    diff_text = _get_diff(args)
    if not diff_text.strip():
        review_md = f"{MARKER}\n# 🤖 AI-ревью PR — {cfg.name}\n\nDiff пустой — нечего ревьюить."
        _write(args.out, review_md)
        print(review_md)
        return 0

    if args.no_index and os.path.exists(cfg.db_path):
        conn = store.connect(cfg.db_path)
        n = store.count(conn)
        conn.close()
        logging.info("[INDEX] reusing existing index (%d chunks) at %s", n, cfg.db_path)
    else:
        n = build_index(cfg)
        logging.info("[INDEX] built (%d chunks)", n)

    result = review_diff(cfg, diff_text)
    review_md = _render(result, cfg)
    _write(args.out, review_md)
    print(review_md)
    return 0


def _write(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
