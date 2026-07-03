"""Vector search: embed query via Ollama, cosine-rank chunks from SQLite."""

import logging
import math
import os
import sys

_PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT_DIR not in sys.path:
    sys.path.insert(0, _PARENT_DIR)

from database import get_connection, load_chunks  # noqa: E402
from embedder import get_embedding  # noqa: E402

DB_PATH = os.path.join(_PARENT_DIR, "rag_wonderland.db")

logger = logging.getLogger(__name__)

STRATEGY_TABLES = {
    "fixed": "chunks_fixed",
    "structural": "chunks_structural",
}


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def retrieve_chunks(query_text: str, strategy: str = "structural", top_k: int = 3, db_path: str = DB_PATH) -> list[dict]:
    """Embed query_text, compare against all chunk embeddings for `strategy`, return top_k.

    Each result dict: {chunk_id, text, meta_source, meta_file, meta_section, score}.
    """
    if strategy not in STRATEGY_TABLES:
        raise ValueError(f"Unknown strategy '{strategy}', expected one of {list(STRATEGY_TABLES)}")
    table = STRATEGY_TABLES[strategy]

    query_vec = get_embedding(query_text)
    if query_vec is None:
        logger.warning("Ollama unavailable — cannot embed query, returning no chunks")
        return []

    conn = get_connection(db_path)
    try:
        chunks = load_chunks(conn, table)
    finally:
        conn.close()

    scored = []
    for chunk in chunks:
        emb = chunk.get("embedding")
        if not emb:
            continue
        score = cosine_similarity(query_vec, emb)
        scored.append({
            "chunk_id": chunk["chunk_id"],
            "text": chunk["text"],
            "meta_source": chunk.get("meta_source", ""),
            "meta_file": chunk.get("meta_file", ""),
            "meta_section": chunk.get("meta_section", ""),
            "score": score,
        })

    scored.sort(key=lambda r: r["score"], reverse=True)
    top = scored[:top_k]

    logger.info("retrieve_chunks(strategy=%s, top_k=%d) query=%r", strategy, top_k, query_text[:80])
    for r in top:
        logger.info("  [%.4f] %s — %s", r["score"], r["chunk_id"], r["meta_section"])

    return top
