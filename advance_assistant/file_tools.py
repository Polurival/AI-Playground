"""Workspace file operations. Every path goes through `_safe_path`, which confines access to the
workspace root (path-traversal guard) — the assistant can never touch files outside it."""

from __future__ import annotations

import difflib
import re
from pathlib import Path

EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv"}
MAX_READ_BYTES = 200_000


def _safe_path(root: str, rel_path: str) -> Path:
    root_p = Path(root).resolve()
    target = (root_p / rel_path).resolve()
    if target != root_p and root_p not in target.parents:
        raise ValueError(f"path escapes workspace: {rel_path!r}")
    return target


def list_files(root: str, glob: str = "**/*") -> list[str]:
    root_p = Path(root).resolve()
    out = []
    for p in root_p.glob(glob or "**/*"):
        if p.is_file():
            rel = p.relative_to(root_p).as_posix()
            if not set(Path(rel).parts) & EXCLUDE_DIRS:
                out.append(rel)
    return sorted(out)


def read_file(root: str, rel_path: str) -> str:
    target = _safe_path(root, rel_path)
    if not target.is_file():
        raise FileNotFoundError(f"no such file: {rel_path}")
    if target.stat().st_size > MAX_READ_BYTES:
        raise ValueError(f"file too large ({target.stat().st_size} bytes): {rel_path}")
    text = target.read_text(encoding="utf-8", errors="replace")
    width = len(str(len(text.splitlines()))) or 1
    return "\n".join(f"{i:>{width}}\t{l}" for i, l in enumerate(text.splitlines(), 1))


def search_files(root: str, pattern: str, glob: str = "**/*", ignore_case: bool = True) -> list[str]:
    try:
        rx = re.compile(pattern, re.IGNORECASE if ignore_case else 0)
    except re.error as exc:
        raise ValueError(f"bad regex {pattern!r}: {exc}") from exc
    hits = []
    for rel in list_files(root, glob):
        try:
            text = _safe_path(root, rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                hits.append(f"{rel}:{n}: {line.rstrip()}")
    return hits


def write_file(root: str, rel_path: str, content: str, append: bool = False) -> str:
    """Create/overwrite (or append to) a file. Returns a status line plus a diff for overwrites."""
    target = _safe_path(root, rel_path)
    existed = target.is_file()
    old = target.read_text(encoding="utf-8", errors="replace") if existed else ""
    new = old + content if append else content
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(new, encoding="utf-8")
    verb = "appended to" if append and existed else "overwrote" if existed else "created"
    status = f"{verb} {rel_path} ({len(new.splitlines())} lines, {len(new)} bytes)"
    if existed and old != new:
        diff = "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                            f"a/{rel_path}", f"b/{rel_path}"))
        status += "\n" + diff[:3000]
    return status
