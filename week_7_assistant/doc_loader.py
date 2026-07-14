"""Turn a target project's documentation files into RAG chunks.

Walks the repo for the configured doc globs (README + docs/** + schema/API files), reads each
file, and splits Markdown by its heading structure so every chunk carries a meaningful section
label (used later as a citation). Oversized sections are further split by size with overlap so
no single chunk blows past the embedder's useful window.

Chunk shape matches `week_5_RAG/database.save_chunks`:
    {chunk_id, text, meta_source, meta_file, meta_section}
(the `embedding` key is added later by ingest.py).
"""

import glob
import logging
import os
import re

from config import ProjectConfig

logger = logging.getLogger(__name__)

MAX_SECTION_CHARS = 3500   # sections longer than this get sub-split
OVERLAP_CHARS = 300        # overlap between sub-splits so a fact on a boundary isn't lost

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def find_doc_files(cfg: ProjectConfig) -> list[str]:
    """Return absolute paths of every doc file matched by the config globs, de-duplicated,
    with excluded directories filtered out."""
    seen: set[str] = set()
    files: list[str] = []
    for pattern in cfg.doc_globs:
        for path in glob.glob(os.path.join(cfg.repo_path, pattern), recursive=True):
            if not os.path.isfile(path):
                continue
            rel_parts = set(os.path.relpath(path, cfg.repo_path).split(os.sep))
            if rel_parts & cfg.exclude_dirs:
                continue
            ap = os.path.abspath(path)
            if ap not in seen:
                seen.add(ap)
                files.append(ap)
    files.sort()
    logger.info("[LOAD] matched %d doc files under %s", len(files), cfg.repo_path)
    return files


def _split_markdown_sections(text: str) -> list[tuple[str, str]]:
    """Split Markdown into (section_label, body) pairs by heading lines.

    The label is a breadcrumb of the enclosing headings, e.g. "Tutorial > Arguments > Optional".
    Content before the first heading is returned under the "(intro)" label.
    """
    sections: list[tuple[str, str]] = []
    heading_stack: list[tuple[int, str]] = []   # (level, title)
    buf: list[str] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        buf.clear()
        if not body:
            return
        label = " > ".join(title for _, title in heading_stack) or "(intro)"
        sections.append((label, body))

    for line in text.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            flush()
            level = len(m.group(1))
            title = m.group(2).strip()
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))
        else:
            buf.append(line)
    flush()
    return sections


def _size_split(body: str, max_chars: int = MAX_SECTION_CHARS, overlap: int = OVERLAP_CHARS) -> list[str]:
    """Split an oversized section body into overlapping windows on paragraph boundaries."""
    if len(body) <= max_chars:
        return [body]
    parts: list[str] = []
    start = 0
    while start < len(body):
        end = min(start + max_chars, len(body))
        # try to break on the last paragraph/newline inside the window
        if end < len(body):
            nl = body.rfind("\n\n", start, end)
            if nl == -1:
                nl = body.rfind("\n", start, end)
            if nl > start:
                end = nl
        parts.append(body[start:end].strip())
        if end >= len(body):
            break
        start = max(end - overlap, start + 1)
    return [p for p in parts if p]


def load_chunks(cfg: ProjectConfig) -> list[dict]:
    """Read every doc file and return the full list of RAG chunks for the project."""
    chunks: list[dict] = []
    for path in find_doc_files(cfg):
        rel = os.path.relpath(path, cfg.repo_path)
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as exc:
            logger.warning("[LOAD] skip %s: %s", rel, exc)
            continue

        if not text.strip():
            continue

        for section_label, body in _split_markdown_sections(text):
            for i, piece in enumerate(_size_split(body)):
                idx = len(chunks)
                chunks.append({
                    "chunk_id": f"{rel}#{idx}",
                    "text": piece,
                    "meta_source": cfg.name,
                    "meta_file": rel,
                    "meta_section": section_label,
                })
    logger.info("[LOAD] produced %d chunks from %s", len(chunks), cfg.name)
    return chunks
