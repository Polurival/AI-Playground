"""Pure file operations the assistant works through — no LLM here.

Every function takes the project `root` and a path *relative to that root*, and every path is
run through `_safe_path`, which resolves it and refuses anything that escapes the root (a path
traversal guard). This is the single choke point for reading and writing, so the assistant can
never touch a file outside the project it was pointed at.

The MCP server (`file_mcp_server.py`) is a thin wrapper over these functions; keeping the logic
here means it is import-testable without spinning up the MCP transport.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

# Directories never walked or written, regardless of the include globs.
EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
DEFAULT_GLOBS = ["**/*.py", "**/*.md", "**/*.txt", "**/*.toml", "**/*.cfg"]

MAX_READ_BYTES = 200_000     # refuse to slurp huge/binary files into the prompt


def _safe_path(root: str, rel_path: str) -> Path:
    """Resolve `rel_path` under `root`, refusing anything that escapes the root."""
    root_p = Path(root).resolve()
    target = (root_p / rel_path).resolve()
    if target != root_p and root_p not in target.parents:
        raise ValueError(f"path escapes project root: {rel_path!r}")
    return target


def _excluded(rel_path: str) -> bool:
    parts = set(Path(rel_path).parts)
    return bool(parts & EXCLUDE_DIRS)


def list_files(root: str, globs: list[str] | None = None) -> list[str]:
    """Return project-relative paths matching any of `globs` (default: code + docs)."""
    root_p = Path(root).resolve()
    globs = globs or DEFAULT_GLOBS
    seen: set[str] = set()
    for pattern in globs:
        for p in root_p.glob(pattern):
            if not p.is_file():
                continue
            rel = p.relative_to(root_p).as_posix()
            if _excluded(rel):
                continue
            seen.add(rel)
    return sorted(seen)


def read_file(root: str, rel_path: str, with_line_numbers: bool = True) -> str:
    """Return the file's text. With line numbers by default (so the model can cite file:line)."""
    target = _safe_path(root, rel_path)
    if not target.is_file():
        raise FileNotFoundError(f"no such file: {rel_path}")
    if target.stat().st_size > MAX_READ_BYTES:
        raise ValueError(f"file too large to read ({target.stat().st_size} bytes): {rel_path}")
    text = target.read_text(encoding="utf-8", errors="replace")
    if not with_line_numbers:
        return text
    lines = text.splitlines()
    width = len(str(len(lines))) if lines else 1
    return "\n".join(f"{i:>{width}}\t{line}" for i, line in enumerate(lines, 1))


def search_files(root: str, pattern: str, globs: list[str] | None = None,
                 ignore_case: bool = False) -> list[dict]:
    """Regex-search across files; return [{path, line, text}] matches (multi-file grep)."""
    flags = re.IGNORECASE if ignore_case else 0
    try:
        rx = re.compile(pattern, flags)
    except re.error as exc:
        raise ValueError(f"bad regex {pattern!r}: {exc}") from exc
    hits: list[dict] = []
    for rel in list_files(root, globs):
        target = _safe_path(root, rel)
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                hits.append({"path": rel, "line": lineno, "text": line.rstrip()})
    return hits


def analyze_project(root: str, globs: list[str] | None = None) -> dict:
    """Summary of the project: file count, per-extension counts, total lines, entry points."""
    files = list_files(root, globs)
    by_ext: dict[str, int] = {}
    total_lines = 0
    entry_points: list[str] = []
    for rel in files:
        ext = Path(rel).suffix or "(none)"
        by_ext[ext] = by_ext.get(ext, 0) + 1
        target = _safe_path(root, rel)
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        total_lines += len(text.splitlines())
        if '__name__ == "__main__"' in text or "__name__ == '__main__'" in text:
            entry_points.append(rel)
    return {
        "root": str(Path(root).resolve()),
        "file_count": len(files),
        "by_extension": dict(sorted(by_ext.items())),
        "total_lines": total_lines,
        "entry_points": sorted(entry_points),
        "files": files,
    }


def unified_diff(root: str, rel_path: str, new_content: str) -> str:
    """Unified diff of `rel_path` (current on disk) vs `new_content`, WITHOUT writing."""
    import difflib

    target = _safe_path(root, rel_path)
    old = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
    old_lines = old.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    label = "(new file)" if not target.is_file() else rel_path
    diff = difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"a/{rel_path}" if target.is_file() else "/dev/null",
        tofile=f"b/{rel_path}",
    )
    out = "".join(diff)
    if not out:
        return f"(no changes to {rel_path})"
    return f"--- {label}\n{out}" if not out.startswith("---") else out


def write_file(root: str, rel_path: str, content: str) -> str:
    """Create/overwrite a file under the root. Returns a short status string."""
    target = _safe_path(root, rel_path)
    existed = target.is_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    n = len(content.splitlines())
    verb = "overwrote" if existed else "created"
    return f"{verb} {rel_path} ({n} lines, {len(content)} bytes)"
