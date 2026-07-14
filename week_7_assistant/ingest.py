"""Ingest a project's docs into a per-project SQLite vector store.

Pipeline: doc_loader.load_chunks -> embed each chunk with Ollama `nomic-embed-text`
(prefixed `search_document:`, the retrieval-side prefix the model was trained with — mirrors the
`search_query:` prefix used at query time in rag.py) -> save to the project's own db/table.

Reuses week_5_RAG's `database` (schema + save) and `embedder.get_embedding` (Ollama call);
only the task-prefix wrapping and table bootstrap are added here.
"""

import json
import logging

import _bootstrap  # noqa: F401 — sets sys.path for the reused week_5 modules

from database import get_connection, save_chunks, CREATE_TABLE
from embedder import get_embedding

from config import ProjectConfig
from doc_loader import load_chunks

logger = logging.getLogger(__name__)

# nomic-embed-text is an asymmetric model: documents and queries must be prefixed differently.
DOC_PREFIX = "search_document: "


def embed_document(text: str) -> list[float] | None:
    """Embed a corpus chunk with the document-side task prefix."""
    return get_embedding(DOC_PREFIX + text)


def _ensure_table(conn, table: str) -> None:
    conn.execute(CREATE_TABLE.format(table=table))
    conn.commit()


def ingest_project(cfg: ProjectConfig) -> int:
    """Load, embed, and store all doc chunks for `cfg`. Returns the number of chunks stored.

    Raises RuntimeError if Ollama produced no embeddings at all (so a silent empty index can't
    slip into production) — a single failed chunk is tolerated and logged.
    """
    chunks = load_chunks(cfg)
    if not chunks:
        raise RuntimeError(
            f"No doc chunks found for '{cfg.name}' under {cfg.repo_path}. "
            f"Check --repo path and doc globs {cfg.doc_globs}."
        )

    logger.info("[INGEST] embedding %d chunks via nomic-embed-text ...", len(chunks))
    embedded = 0
    for i, chunk in enumerate(chunks, 1):
        vec = embed_document(chunk["text"])
        chunk["embedding"] = json.dumps(vec)
        if vec is not None:
            embedded += 1
        if i % 25 == 0 or i == len(chunks):
            logger.info("[INGEST] %d/%d embedded (%d ok)", i, len(chunks), embedded)

    if embedded == 0:
        raise RuntimeError(
            "Every embedding came back empty — is Ollama running and `nomic-embed-text` pulled? "
            "`sudo snap start ollama` (or `ollama serve`), then `ollama pull nomic-embed-text`."
        )

    conn = get_connection(cfg.db_path)
    try:
        _ensure_table(conn, cfg.table)
        # Fresh index each run: drop old rows so deleted/renamed docs don't linger.
        conn.execute(f"DELETE FROM {cfg.table}")
        conn.commit()
        save_chunks(conn, chunks, cfg.table)
    finally:
        conn.close()

    logger.info("[INGEST] stored %d chunks (%d embedded) -> %s [%s]",
                len(chunks), embedded, cfg.db_path, cfg.table)
    return len(chunks)
