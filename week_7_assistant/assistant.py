"""The /help brain: answer a developer's question about the project, grounded in its docs (RAG)
and its live git state (MCP).

Flow:
  question -> query rewrite (project-agnostic) -> RAG retrieve over the project's docs
           -> HARD threshold: if nothing relevant, refuse (never call the LLM to invent an answer)
           -> otherwise build a grounded prompt (doc excerpts + git context) -> LLM answer.

LLM calls go through week_5's `llm_provider`, so the same code answers via DeepSeek (cloud) or a
local Ollama model — switch with `set_provider("local"|"deepseek")`.
"""

import logging

import _bootstrap  # noqa: F401 — sets sys.path for the reused week_5 modules

import llm_provider

from config import ProjectConfig
from rag import retrieve
import git_context

logger = logging.getLogger(__name__)

REWRITE_SYSTEM_PROMPT = (
    "You rewrite a developer's question about a software project so it works well as a query for "
    "semantic search over that project's documentation (README, docs/, schemas).\n"
    "- Keep technical terms, file names, API names, and code identifiers EXACTLY as written.\n"
    "- Make the query dense with the key nouns it is about; drop filler.\n"
    "- Keep it a single question; do not answer it.\n"
    "- If it is already a good search query, return it UNCHANGED.\n"
    "- Output ONLY the rewritten query — no quotes, no preamble."
)

ANSWER_SYSTEM_PROMPT = (
    "You are a developer assistant for the software project named {name}. Answer the developer's "
    "question using ONLY the documentation excerpts and the live git context provided below.\n"
    "- Ground every claim in the excerpts; cite the source file(s) you used, e.g. (docs/index.md).\n"
    "- Use the git context to answer live questions (current branch, recent changes).\n"
    "- If the provided material does not contain the answer, say so plainly and do not invent it.\n"
    "- Be concise and practical; prefer concrete steps, commands, and file references."
)


def _rewrite(question: str) -> str:
    try:
        raw = llm_provider.chat_completion(
            messages=[
                {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
            max_tokens=120,
            temperature=0.0,
        )
    except Exception as exc:
        logger.warning("[HELP] query rewrite failed (%s) — using original question", exc)
        return question
    rewritten = (raw or "").strip().strip('"')
    if rewritten and rewritten != question:
        logger.info("[HELP] rewrite: %r -> %r", question, rewritten)
    return rewritten or question


def _build_doc_context(kept: list[dict]) -> str:
    blocks = []
    for i, c in enumerate(kept, 1):
        blocks.append(
            f"[{i}] file: {c['meta_file']} | section: {c['meta_section']} "
            f"(cosine={c['score']:.3f})\n{c['text']}"
        )
    return "\n\n".join(blocks)


def refusal(cfg: ProjectConfig) -> str:
    return (
        f"I couldn't find anything in {cfg.name}'s documentation relevant enough to answer that. "
        f"Try rephrasing, or ask about a topic the README/docs actually cover."
    )


def answer_help(
    cfg: ProjectConfig,
    question: str,
    include_diff: bool = False,
    include_files: bool = False,
    max_tokens: int = 700,
) -> dict:
    """Answer one /help question. Returns a dict with the answer plus diagnostics/sources."""
    rewritten = _rewrite(question)
    search = retrieve(cfg, rewritten)

    # Git context is always fetched (via MCP) so branch/status questions work even when the docs
    # threshold fails — it is cheap and does not require an LLM call.
    git_block = git_context.gather_context(cfg.repo_path, include_diff=include_diff, include_files=include_files)

    if not search["threshold_passed"] or not search["kept"]:
        logger.info("[HELP] hard threshold failed (max cosine %.4f) — refusing", search["max_score"])
        return {
            "answer": refusal(cfg),
            "sources": [],
            "rewritten_query": rewritten,
            "max_score": search["max_score"],
            "threshold_passed": False,
            "git_context": git_block,
            "provider": llm_provider.current_label(),
        }

    kept = search["kept"]
    doc_context = _build_doc_context(kept)
    user_prompt = (
        f"# Documentation excerpts\n{doc_context}\n\n"
        f"# Live git context (via MCP)\n{git_block}\n\n"
        f"# Developer's question\n{question}"
    )

    answer = llm_provider.chat_completion(
        messages=[
            {"role": "system", "content": ANSWER_SYSTEM_PROMPT.format(name=cfg.name)},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=max_tokens,
        temperature=0.2,
    )

    sources = [
        {"chunk_id": c["chunk_id"], "meta_file": c["meta_file"], "meta_section": c["meta_section"],
         "score": c["score"], "rerank_score": c.get("rerank_score")}
        for c in kept
    ]
    return {
        "answer": answer.strip() or refusal(cfg),
        "sources": sources,
        "rewritten_query": rewritten,
        "max_score": search["max_score"],
        "threshold_passed": True,
        "git_context": git_block,
        "provider": llm_provider.current_label(),
    }
