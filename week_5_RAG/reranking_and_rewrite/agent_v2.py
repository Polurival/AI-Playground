"""Agent v2: 'basic' RAG (Task 2, unchanged) vs 'advanced' RAG (rewrite + broad search + rerank)."""

import logging
import os
import sys

_REQUEST_TO_RAG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "request_to_RAG")
if _REQUEST_TO_RAG_DIR not in sys.path:
    sys.path.insert(0, _REQUEST_TO_RAG_DIR)

from agent import ask_agent as ask_agent_basic, build_context  # noqa: E402 — reused from Task 2
from generation import generate_answer  # noqa: E402 — reused from Task 2

from query_rewrite import rewrite_query
from retrieval_v2 import retrieve_chunks_advanced, TOP_K_FINAL, TOP_K_INITIAL

logger = logging.getLogger(__name__)


def ask_agent_v2(
    question: str,
    mode: str = "advanced",
    strategy: str = "structural",
    top_k_initial: int = TOP_K_INITIAL,
    top_k_final: int = TOP_K_FINAL,
    language: str | None = None,
) -> dict:
    """mode='basic'    -> original question -> retrieve top-3 -> LLM (Task 2 behaviour, untouched).
    mode='advanced' -> question -> Query Rewrite -> retrieve top-10 -> cross-encoder rerank
                       to top-3 -> LLM (answer grounded on ORIGINAL question, retrieval driven by
                       the rewritten one).

    `language`, if given (e.g. "English"), forces the final answer's language regardless of
    what language the question/context happens to be in. Default None leaves the model's
    natural choice untouched.

    Returns a dict shared by both modes:
        {answer, sources, rewritten_query, initial_count, dropped_count, final_count}
    """
    if mode == "basic":
        logger.info("[AGENT] mode=basic — plain top-3 retrieval, no rewrite/rerank")
        result = ask_agent_basic(question, use_rag=True, strategy=strategy, top_k=top_k_final, language=language)
        return {
            "answer": result["answer"],
            "sources": result["sources"],
            "rewritten_query": question,
            "initial_count": len(result["sources"]),
            "dropped_count": 0,
            "final_count": len(result["sources"]),
        }

    if mode != "advanced":
        raise ValueError(f"Unknown mode '{mode}', expected 'basic' or 'advanced'")

    logger.info("[AGENT] mode=advanced — rewrite + broad search + rerank")
    rewritten = rewrite_query(question)

    search_result = retrieve_chunks_advanced(
        rewritten, strategy=strategy, top_k_initial=top_k_initial, top_k_final=top_k_final
    )
    kept = search_result["kept"]

    if not kept:
        logger.warning("[AGENT] no chunks survived retrieval — falling back to context-free answer")
        answer = generate_answer(question, context=None, language=language)
        return {
            "answer": answer,
            "sources": [],
            "rewritten_query": rewritten,
            "initial_count": search_result["initial_count"],
            "dropped_count": search_result["dropped_count"],
            "final_count": 0,
        }

    context = build_context(kept)
    answer = generate_answer(question, context=context, language=language)
    sources = [
        {"chunk_id": c["chunk_id"], "meta_section": c["meta_section"], "score": c["score"], "rerank_score": c.get("rerank_score")}
        for c in kept
    ]

    return {
        "answer": answer,
        "sources": sources,
        "rewritten_query": rewritten,
        "initial_count": search_result["initial_count"],
        "dropped_count": search_result["dropped_count"],
        "final_count": len(kept),
    }
