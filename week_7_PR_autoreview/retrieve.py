"""Retrieval over the corpus index: embed a query, cosine-rank all chunks, return the top-k.

Embeddings are stored normalized, so cosine similarity is a plain dot product. The corpus is small
(a single repo), so a linear scan is instant and needs no vector-DB dependency.
"""

import logging

from config import ReviewConfig
from embeddings import embed_query

logger = logging.getLogger(__name__)


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def retrieve(cfg: ReviewConfig, all_chunks: list[dict], query: str, top_k: int) -> list[dict]:
    """Return the top-k chunks most similar to ``query``. ``all_chunks`` is the loaded index
    (passed in so the caller loads the store once and reuses it across many changed files)."""
    qvec = embed_query(query, cfg.embed_model)
    scored = []
    for c in all_chunks:
        emb = c.get("embedding")
        if not emb:
            continue
        scored.append((_dot(qvec, emb), c))
    scored.sort(key=lambda t: t[0], reverse=True)
    out = []
    for score, c in scored[:top_k]:
        item = dict(c)
        item["score"] = score
        out.append(item)
    return out
