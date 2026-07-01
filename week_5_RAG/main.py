"""End-to-end RAG indexing pipeline for Alice's Adventures in Wonderland."""

import logging
import os
import sys

from epub_parser import parse_epub, EPUB_PATH, SOURCE_NAME
from chunkers import fixed_chunks, structural_chunks
from embedder import embed_chunks
from database import get_connection, init_db, save_chunks
from analysis import print_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    # ── Step 1: Parse EPUB ──────────────────────────────────────────────────
    if not os.path.exists(EPUB_PATH):
        logger.error("EPUB not found: %s", EPUB_PATH)
        sys.exit(1)

    logger.info("Parsing EPUB: %s", EPUB_PATH)
    chapters = parse_epub(EPUB_PATH)
    logger.info("Extracted %d chapters", len(chapters))
    for i, ch in enumerate(chapters):
        logger.info("  ch%02d [%d chars] %s", i, len(ch["text"]), ch["title"][:60])

    # Attach source filename to every chapter
    for ch in chapters:
        ch["source"] = SOURCE_NAME

    # ── Step 2: Chunking ────────────────────────────────────────────────────
    logger.info("Creating fixed-size chunks (1000 chars, 180 overlap) …")
    fixed = fixed_chunks(chapters)
    logger.info("Fixed-size: %d chunks", len(fixed))

    logger.info("Creating structural chunks (chapter-based, max 4000 chars) …")
    structural = structural_chunks(chapters)
    logger.info("Structural: %d chunks", len(structural))

    # ── Step 3: Embeddings ──────────────────────────────────────────────────
    logger.info("Embedding fixed-size chunks via Ollama nomic-embed-text …")
    fixed = embed_chunks(fixed, label="fixed")

    logger.info("Embedding structural chunks via Ollama nomic-embed-text …")
    structural = embed_chunks(structural, label="structural")

    # ── Step 4: Store in SQLite ─────────────────────────────────────────────
    conn = get_connection()
    init_db(conn)
    save_chunks(conn, fixed, "chunks_fixed")
    save_chunks(conn, structural, "chunks_structural")
    conn.close()
    logger.info("All data saved to rag_wonderland.db")

    # ── Step 5: Comparison report ───────────────────────────────────────────
    print_report(fixed, structural)


if __name__ == "__main__":
    main()
