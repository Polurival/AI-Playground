"""Agent v2: 'basic' RAG (Task 2, unchanged) vs 'advanced' RAG (rewrite + broad search + rerank)."""

import logging
import os
import sys

_REQUEST_TO_RAG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "request_to_RAG")
if _REQUEST_TO_RAG_DIR not in sys.path:
    sys.path.insert(0, _REQUEST_TO_RAG_DIR)

from agent import ask_agent as ask_agent_basic  # noqa: E402 — reused from Task 2
from generation import generate_answer  # noqa: E402 — reused from Task 2

from generation_v3 import generate_structured_answer
from query_rewrite import rewrite_query
from retrieval_v2 import retrieve_chunks_advanced, SIMILARITY_THRESHOLD, TOP_K_FINAL, TOP_K_INITIAL

logger = logging.getLogger(__name__)

HARD_REFUSAL_ANSWER = (
    "Unfortunately, 'Alice's Adventures in Wonderland' does not contain enough facts to answer "
    "this question. Please rephrase or clarify your request."
)


def ask_agent_v2(
    question: str,
    mode: str = "advanced",
    strategy: str = "structural",
    top_k_initial: int = TOP_K_INITIAL,
    top_k_final: int = TOP_K_FINAL,
    language: str | None = None,
) -> dict:
    """mode='basic'    -> original question -> retrieve top-3 -> LLM (Task 2 behaviour, untouched).
    mode='advanced' -> question -> Query Rewrite -> retrieve top-10 -> HARD relevance threshold
                       (SIMILARITY_THRESHOLD cosine) -> cross-encoder rerank to top-3 ->
                       structured LLM answer (Ответ / Использованные цитаты / Источники).
                       If no candidate clears the threshold, the DeepSeek API is NEVER called —
                       a canned "I don't know" answer (HARD_REFUSAL_ANSWER) is returned instead.

    `language`, if given (e.g. "English"), forces the final answer's language regardless of
    what language the question/context happens to be in. Default None leaves the model's
    natural choice untouched.

    Returns a dict shared by both modes:
        {answer, sources, rewritten_query, initial_count, dropped_count, final_count,
         max_score, threshold_passed, hard_refusal}
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
            "max_score": None,
            "threshold_passed": None,
            "hard_refusal": False,
        }

    if mode != "advanced":
        raise ValueError(f"Unknown mode '{mode}', expected 'basic' or 'advanced'")

    logger.info("[AGENT] mode=advanced — rewrite + broad search + hard threshold + rerank + structured answer")
    rewritten = rewrite_query(question)

    search_result = retrieve_chunks_advanced(
        rewritten, strategy=strategy, top_k_initial=top_k_initial, top_k_final=top_k_final
    )
    max_score = search_result["max_score"]
    threshold_passed = search_result["threshold_passed"]

    if not threshold_passed:
        logger.warning(
            "[AGENT] HARD THRESHOLD FAILED (max cosine %.4f < %.2f) — refusing to call DeepSeek, "
            "returning canned 'I don't know' answer",
            max_score, SIMILARITY_THRESHOLD,
        )
        return {
            "answer": HARD_REFUSAL_ANSWER,
            "sources": [],
            "rewritten_query": rewritten,
            "initial_count": search_result["initial_count"],
            "dropped_count": search_result["initial_count"],
            "final_count": 0,
            "max_score": max_score,
            "threshold_passed": False,
            "hard_refusal": True,
        }

    logger.info("[AGENT] HARD THRESHOLD PASSED (max cosine %.4f >= %.2f) — proceeding to rerank + LLM", max_score, SIMILARITY_THRESHOLD)
    kept = search_result["kept"]

    if not kept:
        logger.warning("[AGENT] threshold passed but reranker kept nothing — falling back to context-free answer")
        answer = generate_answer(question, context=None, language=language)
        return {
            "answer": answer,
            "sources": [],
            "rewritten_query": rewritten,
            "initial_count": search_result["initial_count"],
            "dropped_count": search_result["dropped_count"],
            "final_count": 0,
            "max_score": max_score,
            "threshold_passed": True,
            "hard_refusal": False,
        }

    answer = generate_structured_answer(question, kept, language=language)
    sources = [
        {
            "chunk_id": c["chunk_id"],
            "meta_source": c["meta_source"],
            "meta_section": c["meta_section"],
            "score": c["score"],
            "rerank_score": c.get("rerank_score"),
        }
        for c in kept
    ]

    return {
        "answer": answer,
        "sources": sources,
        "rewritten_query": rewritten,
        "initial_count": search_result["initial_count"],
        "dropped_count": search_result["dropped_count"],
        "final_count": len(kept),
        "max_score": max_score,
        "threshold_passed": True,
        "hard_refusal": False,
    }
