"""Two-stage retrieval: broad recall (top_k_initial, cosine) -> cross-encoder rerank -> top_k_final."""

import logging
import os
import sys

_REQUEST_TO_RAG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "request_to_RAG")
if _REQUEST_TO_RAG_DIR not in sys.path:
    sys.path.insert(0, _REQUEST_TO_RAG_DIR)

from retrieval import retrieve_chunks  # noqa: E402 — reused base retrieval from Task 2

logger = logging.getLogger(__name__)

TOP_K_INITIAL = 10
TOP_K_FINAL = 3
RERANKER_MODEL_NAME = "BAAI/bge-reranker-base"

_reranker = None  # lazy singleton — loaded once, reused across calls


def _get_reranker():
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder

        logger.info("[RERANK] loading cross-encoder %s (first call only) ...", RERANKER_MODEL_NAME)
        _reranker = CrossEncoder(RERANKER_MODEL_NAME)
    return _reranker


def rerank_with_cross_encoder(query_text: str, candidates: list[dict], top_k_final: int = TOP_K_FINAL) -> dict:
    """Score every (query, chunk_text) pair with a real cross-encoder and keep the top_k_final
    by that score — the model judges relevance directly, unlike the cosine similarity used for
    broad recall.

    Falls back to the existing cosine order if the reranker can't be loaded (e.g. offline,
    missing weights) so the pipeline never breaks, it just loses the reranking benefit.

    Returns {"kept": list[dict], "initial_count": int, "final_count": int, "dropped_count": int}.
    """
    if not candidates:
        return {"kept": [], "initial_count": 0, "final_count": 0, "dropped_count": 0}

    try:
        model = _get_reranker()
        pairs = [(query_text, c["text"]) for c in candidates]
        scores = model.predict(pairs)
    except Exception as exc:
        logger.warning("[RERANK] cross-encoder unavailable (%s) — falling back to cosine order", exc)
        kept = candidates[:top_k_final]
        return {
            "kept": kept,
            "initial_count": len(candidates),
            "final_count": len(kept),
            "dropped_count": len(candidates) - len(kept),
        }

    for c, s in zip(candidates, scores):
        c["rerank_score"] = float(s)

    ranked = sorted(candidates, key=lambda c: c["rerank_score"], reverse=True)

    logger.info("[RERANK] cross-encoder scored %d candidates:", len(ranked))
    for c in ranked:
        logger.info("  [rerank=%.4f | cosine=%.4f] %s — %s", c["rerank_score"], c["score"], c["chunk_id"], c["meta_section"])

    kept = ranked[:top_k_final]
    dropped_count = len(candidates) - len(kept)
    logger.info("[RERANK] kept top %d by cross-encoder score, %d dropped", len(kept), dropped_count)

    return {"kept": kept, "initial_count": len(candidates), "final_count": len(kept), "dropped_count": dropped_count}


def retrieve_chunks_advanced(
    query_text: str,
    strategy: str = "structural",
    top_k_initial: int = TOP_K_INITIAL,
    top_k_final: int = TOP_K_FINAL,
) -> dict:
    """Stage 1 (broad cosine recall, top_k_initial) + Stage 2 (cross-encoder rerank to top_k_final)."""
    logger.info("[RETRIEVE] broad search top_k=%d (strategy=%s)", top_k_initial, strategy)
    candidates = retrieve_chunks(query_text, strategy=strategy, top_k=top_k_initial)
    return rerank_with_cross_encoder(query_text, candidates, top_k_final=top_k_final)
