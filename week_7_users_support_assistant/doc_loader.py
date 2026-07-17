"""Превращает документацию продукта в чанки для RAG.

Обходит `product_dir` по glob-паттернам из конфига, читает каждый файл и режет Markdown по
структуре заголовков, чтобы у каждого чанка была осмысленная секция — она потом печатается как
ссылка на источник в ответе поддержки. Слишком длинные секции дорезаются по размеру с
перекрытием.

Форма чанка совпадает с `week_5_RAG/database.save_chunks`:
    {chunk_id, text, meta_source, meta_file, meta_section}
(ключ `embedding` добавляет ingest.py).
"""

import glob
import logging
import os
import re

from config import SupportConfig

logger = logging.getLogger(__name__)

MAX_SECTION_CHARS = 3500   # секции длиннее — дорезаем
OVERLAP_CHARS = 300        # перекрытие, чтобы факт на границе не потерялся

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def find_doc_files(cfg: SupportConfig) -> list[str]:
    """Абсолютные пути всех файлов документации по glob-паттернам конфига, без дублей."""
    seen: set[str] = set()
    files: list[str] = []
    for pattern in cfg.doc_globs:
        for path in glob.glob(os.path.join(cfg.product_dir, pattern), recursive=True):
            if not os.path.isfile(path):
                continue
            rel_parts = set(os.path.relpath(path, cfg.product_dir).split(os.sep))
            if rel_parts & cfg.exclude_dirs:
                continue
            ap = os.path.abspath(path)
            if ap not in seen:
                seen.add(ap)
                files.append(ap)
    files.sort()
    logger.info("[LOAD] matched %d doc files under %s", len(files), cfg.product_dir)
    return files


def _split_markdown_sections(text: str) -> list[tuple[str, str]]:
    """Режет Markdown на пары (метка секции, тело) по заголовкам.

    Метка — «хлебные крошки» вложенных заголовков, например
    «Тарифы и лимиты TaskPilot > Корпоративный SSO доступен только на Business».
    Текст до первого заголовка попадает в секцию «(intro)».
    """
    sections: list[tuple[str, str]] = []
    heading_stack: list[tuple[int, str]] = []   # (уровень, заголовок)
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
    """Режет слишком длинную секцию на перекрывающиеся окна по границам абзацев."""
    if len(body) <= max_chars:
        return [body]
    parts: list[str] = []
    start = 0
    while start < len(body):
        end = min(start + max_chars, len(body))
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


def load_chunks(cfg: SupportConfig) -> list[dict]:
    """Читает всю документацию продукта и возвращает список чанков.

    В текст чанка добавляется заголовок «файл :: секция»: корпус небольшой, а вопросы поддержки
    часто формулируются кодом ошибки — заголовок помогает и эмбеддингу, и cross-encoder'у
    отличить SSO-раздел от раздела про пароли.
    """
    chunks: list[dict] = []
    for path in find_doc_files(cfg):
        rel = os.path.relpath(path, cfg.product_dir)
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as exc:
            logger.warning("[LOAD] skip %s: %s", rel, exc)
            continue

        if not text.strip():
            continue

        for section_label, body in _split_markdown_sections(text):
            for piece in _size_split(body):
                idx = len(chunks)
                chunks.append({
                    "chunk_id": f"{rel}#{idx}",
                    "text": f"{rel} :: {section_label}\n\n{piece}",
                    "meta_source": cfg.product_name,
                    "meta_file": rel,
                    "meta_section": section_label,
                })
    logger.info("[LOAD] produced %d chunks from %s", len(chunks), cfg.product_name)
    return chunks
