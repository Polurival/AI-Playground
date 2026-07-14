"""Retrieval for the developer assistant.

Two-stage, same shape as `week_5_RAG/reranking_and_rewrite`:
  1. embed the query (`search_query:` prefix) -> cosine-rank all doc chunks -> broad top_k_initial
  2. HARD relevance threshold: if the best cosine is below `threshold`, abort BEFORE the LLM is
     ever called (so the assistant refuses instead of hallucinating about the project)
  3. cross-encoder rerank the survivors down to top_k_final

Reuses `retrieval.cosine_similarity` and `retrieval_v2.rerank_with_cross_encoder`; only the
per-project table loading and the query-side task prefix are added here.
"""

import logging

import _bootstrap  # noqa: F401 — sets sys.path for the reused week_5 modules

from database import get_connection, load_chunks as _load_chunks
from embedder import get_embedding
from retrieval import cosine_similarity
from retrieval_v2 import rerank_with_cross_encoder

from config import ProjectConfig

logger = logging.getLogger(__name__)

QUERY_PREFIX = "search_query: "     # nomic-embed-text query-side task prefix (pairs with DOC_PREFIX)
TOP_K_INITIAL = 12
TOP_K_FINAL = 4
SIMILARITY_THRESHOLD = 0.55         # below this best-cosine, refuse rather than answer


def embed_query(text: str) -> list[float] | None:
    return get_embedding(QUERY_PREFIX + text)


def retrieve(
    cfg: ProjectConfig,
    query_text: str,
    top_k_initial: int = TOP_K_INITIAL,
    top_k_final: int = TOP_K_FINAL,
    threshold: float = SIMILARITY_THRESHOLD,
) -> dict:
    """Return {kept, max_score, threshold_passed, initial_count, dropped_count}.

    `kept` is the reranked top_k_final list of chunk dicts (empty when the threshold fails or the
    index is empty). Each kept chunk has: chunk_id, text, meta_file, meta_section, score,
    rerank_score.
    """
    empty = {"kept": [], "max_score": 0.0, "threshold_passed": False,
             "initial_count": 0, "dropped_count": 0}

    qvec = embed_query(query_text)
    if qvec is None:
        logger.warning("[RAG] Ollama unavailable — cannot embed query")
        return empty

    conn = get_connection(cfg.db_path)
    try:
        chunks = _load_chunks(conn, cfg.table)
    except Exception as exc:
        logger.warning("[RAG] cannot load table '%s' from %s: %s — was the project ingested?",
                       cfg.table, cfg.db_path, exc)
        return empty
    finally:
        conn.close()

    scored = []
    for c in chunks:
        emb = c.get("embedding")
        if not emb:
            continue
        scored.append({
            "chunk_id": c["chunk_id"],
            "text": c["text"],
            "meta_file": c.get("meta_file", ""),
            "meta_section": c.get("meta_section", ""),
            "score": cosine_similarity(qvec, emb),
        })
    scored.sort(key=lambda r: r["score"], reverse=True)
    candidates = scored[:top_k_initial]

    max_score = candidates[0]["score"] if candidates else 0.0
    passed = bool(candidates) and max_score >= threshold
    logger.info("[RAG] best cosine %.4f vs threshold %.2f -> %s",
                max_score, threshold, "PASS" if passed else "FAIL")

    if not passed:
        return {"kept": [], "max_score": max_score, "threshold_passed": False,
                "initial_count": len(candidates), "dropped_count": len(candidates)}

    rr = rerank_with_cross_encoder(query_text, candidates, top_k_final=top_k_final)
    return {
        "kept": rr["kept"],
        "max_score": max_score,
        "threshold_passed": True,
        "initial_count": len(candidates),
        "dropped_count": len(candidates) - len(rr["kept"]),
    }
