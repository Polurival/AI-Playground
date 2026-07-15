"""Orchestrate the AI code review.

Pipeline:
  1. parse the PR diff into per-file changes
  2. for each changed file, retrieve related repo context (docs + code) from the RAG index,
     using the file path + its added lines as the query
  3. pack the diff + the de-duplicated retrieved context into one prompt
  4. ask the LLM for a structured review: potential bugs / architecture issues / recommendations

Unlike the /help assistant, the reviewer never hard-refuses on weak retrieval: RAG context is
supplementary here — even with no relevant docs, the diff itself is always worth reviewing.
"""

import logging

from config import ReviewConfig
from diff_parser import parse_diff, reviewable_files, FileDiff
from retrieve import retrieve
import store
import llm

logger = logging.getLogger(__name__)


_SYSTEM = {
    "ru": (
        "Ты — старший инженер, делающий ревью Pull Request. Отвечай ТОЛЬКО на основе показанного "
        "diff и контекста репозитория (документация + код). Будь конкретным и практичным, "
        "ссылайся на файлы и строки. Не хвали ради похвалы и не выдумывай проблемы. Если "
        "серьёзных замечаний нет — так и скажи.\n"
        "Верни ревью в формате Markdown РОВНО с этими тремя разделами:\n"
        "## 🐞 Потенциальные баги\n"
        "## 🏛️ Архитектурные проблемы\n"
        "## 💡 Рекомендации\n"
        "В каждом разделе — маркированный список; если замечаний нет, напиши «Не выявлено»."
    ),
    "en": (
        "You are a senior engineer reviewing a Pull Request. Answer ONLY from the shown diff and "
        "the repository context (documentation + code). Be specific and practical, cite files and "
        "lines. Do not praise for the sake of it and do not invent problems. If there are no "
        "serious issues, say so.\n"
        "Return the review as Markdown with EXACTLY these three sections:\n"
        "## 🐞 Potential bugs\n"
        "## 🏛️ Architecture issues\n"
        "## 💡 Recommendations\n"
        "Use a bullet list in each section; if a section has nothing, write \"None found\"."
    ),
}


def _query_for(f: FileDiff) -> str:
    """Build a retrieval query from a changed file: its path plus a slice of its added lines."""
    added = f.added_text.strip()
    return f"{f.path}\n{added[:1200]}"


def _gather_context(cfg: ReviewConfig, files: list[FileDiff]) -> list[dict]:
    """Retrieve related repo context for all changed files, de-duplicated and capped."""
    conn = store.connect(cfg.db_path)
    try:
        all_chunks = store.load_all(conn)
    finally:
        conn.close()
    if not all_chunks:
        logger.warning("[REVIEW] index is empty — reviewing from the diff alone")
        return []

    seen: set[str] = set()
    picked: list[dict] = []
    for f in files:
        for hit in retrieve(cfg, all_chunks, _query_for(f), cfg.top_k_per_file):
            if hit["chunk_id"] in seen:
                continue
            seen.add(hit["chunk_id"])
            picked.append(hit)
    picked.sort(key=lambda c: c["score"], reverse=True)
    return picked[: cfg.max_context_chunks]


def _build_diff_block(files: list[FileDiff], budget: int) -> str:
    """Concatenate the changed files' diffs into the prompt, within a char budget."""
    blocks: list[str] = []
    used = 0
    for f in files:
        header = f"### {f.path}  ({f.status})"
        text = f.diff_text
        block = f"{header}\n```diff\n{text}\n```"
        if used + len(block) > budget:
            remaining = budget - used
            if remaining > 200:
                blocks.append(block[:remaining] + "\n...(diff truncated)")
            blocks.append("\n...(remaining files omitted — diff too large)")
            break
        blocks.append(block)
        used += len(block)
    return "\n\n".join(blocks)


def _build_context_block(chunks: list[dict]) -> str:
    if not chunks:
        return "(нет релевантного контекста из репозитория / no relevant repo context)"
    blocks = []
    for i, c in enumerate(chunks, 1):
        blocks.append(f"[{i}] {c['file']} :: {c['section']} (score={c['score']:.3f})\n{c['text']}")
    return "\n\n".join(blocks)


def review_diff(cfg: ReviewConfig, diff_text: str) -> dict:
    """Run the full review on a unified diff. Returns {review, files, sources}."""
    parsed = parse_diff(diff_text)
    files = reviewable_files(parsed)
    if not files:
        return {"review": _no_changes_note(cfg), "files": [], "sources": []}

    context = _gather_context(cfg, files)
    diff_block = _build_diff_block(files, cfg.max_diff_chars)
    context_block = _build_context_block(context)

    file_list = ", ".join(f.path for f in files)
    user_prompt = (
        f"# Файлы в PR / Changed files\n{file_list}\n\n"
        f"# Diff\n{diff_block}\n\n"
        f"# Контекст репозитория (RAG: документация + код) / Repository context\n{context_block}"
    )

    client = llm.make_client(cfg)
    system = _SYSTEM.get(cfg.review_lang, _SYSTEM["en"])
    review = llm.chat(cfg, client, system, user_prompt).strip()

    sources = [{"file": c["file"], "section": c["section"], "score": c["score"]} for c in context]
    return {"review": review, "files": [f.path for f in files], "sources": sources}


def _no_changes_note(cfg: ReviewConfig) -> str:
    if cfg.review_lang == "ru":
        return "В этом PR нет изменений кода для ревью (только удаления/бинарные файлы)."
    return "This PR has no reviewable code changes (only deletions / binary files)."
