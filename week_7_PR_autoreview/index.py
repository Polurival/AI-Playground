"""Build the RAG index: corpus (docs + code) -> embeddings -> SQLite store.

Runs fresh each time (in CI the checkout is fresh anyway), so the index always matches the exact
code being reviewed. Fast because embeddings are batched on CPU.
"""

import logging

from config import ReviewConfig
from corpus import load_chunks
from embeddings import embed_texts
import store

logger = logging.getLogger(__name__)


def build_index(cfg: ReviewConfig) -> int:
    """Embed the whole corpus and store it. Returns the number of chunks indexed."""
    chunks = load_chunks(cfg)
    if not chunks:
        raise RuntimeError(
            f"No doc/code files found under {cfg.repo_path}. Check --repo and the exclude lists."
        )

    logger.info("[INDEX] embedding %d chunks with %s ...", len(chunks), cfg.embed_model)
    vectors = embed_texts([c["text"] for c in chunks], cfg.embed_model)
    for chunk, vec in zip(chunks, vectors):
        chunk["embedding"] = vec

    conn = store.connect(cfg.db_path)
    try:
        store.replace_all(conn, chunks)
    finally:
        conn.close()

    logger.info("[INDEX] stored %d chunks -> %s", len(chunks), cfg.db_path)
    return len(chunks)
