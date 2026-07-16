"""Turn the target repo into RAG chunks over BOTH documentation and code.

Walks the repo, keeps doc + code files (see extension sets in ``config``), and splits each into
overlapping chunks. Markdown is split by heading first (so a chunk carries a meaningful section
label used as a citation); code and other text are split into line windows labelled by line range.

Chunk shape: ``{chunk_id, text, file, section}`` — the ``embedding`` is added later by ``index``.
"""

import logging
import os
import re

from config import (
    ReviewConfig, DOC_EXTS, CODE_EXTS, DOC_BASENAMES,
    MAX_FILE_BYTES, CHUNK_CHARS, CHUNK_OVERLAP,
)

logger = logging.getLogger(__name__)

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def _wanted(path: str) -> bool:
    base = os.path.basename(path)
    ext = os.path.splitext(base)[1].lower()
    if ext in DOC_EXTS or ext in CODE_EXTS:
        return True
    return base in DOC_BASENAMES  # extensionless docs like README


def find_corpus_files(cfg: ReviewConfig) -> list[str]:
    """Return absolute paths of every doc/code file in the repo, minus excluded dirs/suffixes."""
    files: list[str] = []
    for root, dirs, names in os.walk(cfg.repo_path):
        dirs[:] = [d for d in dirs if d not in cfg.exclude_dirs]
        for name in names:
            if any(name.endswith(sfx) for sfx in cfg.exclude_suffixes):
                continue
            path = os.path.join(root, name)
            if not _wanted(path):
                continue
            try:
                if os.path.getsize(path) > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            files.append(path)
    files.sort()
    logger.info("[CORPUS] matched %d doc/code files under %s", len(files), cfg.repo_path)
    return files


def _read_text(path: str) -> str | None:
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as exc:
        logger.warning("[CORPUS] skip %s: %s", path, exc)
        return None
    if b"\x00" in raw:            # crude binary guard
        return None
    return raw.decode("utf-8", errors="replace")


def _size_split(body: str, max_chars: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping windows, preferring newline boundaries."""
    body = body.strip()
    if len(body) <= max_chars:
        return [body] if body else []
    parts: list[str] = []
    start = 0
    while start < len(body):
        end = min(start + max_chars, len(body))
        if end < len(body):
            nl = body.rfind("\n", start, end)
            if nl > start:
                end = nl
        piece = body[start:end].strip()
        if piece:
            parts.append(piece)
        if end >= len(body):
            break
        start = max(end - overlap, start + 1)
    return parts


def _markdown_sections(text: str) -> list[tuple[str, str]]:
    """Split Markdown into (heading breadcrumb, body) pairs."""
    sections: list[tuple[str, str]] = []
    stack: list[tuple[int, str]] = []
    buf: list[str] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        buf.clear()
        if body:
            label = " > ".join(t for _, t in stack) or "(intro)"
            sections.append((label, body))

    for line in text.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            flush()
            level = len(m.group(1))
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, m.group(2).strip()))
        else:
            buf.append(line)
    flush()
    return sections


def _chunk_file(rel: str, text: str) -> list[tuple[str, str]]:
    """Return (section_label, chunk_text) pairs for one file."""
    ext = os.path.splitext(rel)[1].lower()
    out: list[tuple[str, str]] = []
    if ext == ".md":
        for label, body in _markdown_sections(text):
            for piece in _size_split(body):
                out.append((label, piece))
        return out

    # Code / plain text: window by size, label with the covered line range.
    lines = text.splitlines(keepends=True)
    # Map char offsets back to line numbers for labelling.
    offsets = []
    pos = 0
    for ln in lines:
        offsets.append(pos)
        pos += len(ln)
    joined = "".join(lines)

    for piece in _size_split(joined):
        idx = joined.find(piece)
        start_line = 1
        if idx >= 0:
            start_line = sum(1 for o in offsets if o <= idx)
        end_line = start_line + piece.count("\n")
        out.append((f"lines {start_line}-{end_line}", piece))
    return out


def load_chunks(cfg: ReviewConfig) -> list[dict]:
    """Read the whole corpus and return RAG chunks for the repo."""
    chunks: list[dict] = []
    for path in find_corpus_files(cfg):
        text = _read_text(path)
        if not text or not text.strip():
            continue
        rel = os.path.relpath(path, cfg.repo_path)
        for section, piece in _chunk_file(rel, text):
            chunks.append({
                "chunk_id": f"{rel}#{len(chunks)}",
                "text": piece,
                "file": rel,
                "section": section,
            })
    logger.info("[CORPUS] produced %d chunks from %s", len(chunks), cfg.name)
    return chunks
