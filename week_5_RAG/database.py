"""SQLite storage for RAG chunks with JSON-serialized embeddings."""

import sqlite3
import logging

DB_PATH = "rag_wonderland.db"

logger = logging.getLogger(__name__)

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS {table} (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id    TEXT NOT NULL UNIQUE,
    text        TEXT NOT NULL,
    meta_source TEXT,
    meta_file   TEXT,
    meta_section TEXT,
    embedding   TEXT
)
"""


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute(CREATE_TABLE.format(table="chunks_fixed"))
    cur.execute(CREATE_TABLE.format(table="chunks_structural"))
    conn.commit()
    logger.info("Database initialized: chunks_fixed + chunks_structural tables ready")


def save_chunks(conn: sqlite3.Connection, chunks: list[dict], table: str) -> None:
    cur = conn.cursor()
    rows = [
        (
            c["chunk_id"],
            c["text"],
            c.get("meta_source", ""),
            c.get("meta_file", ""),
            c.get("meta_section", ""),
            c.get("embedding"),
        )
        for c in chunks
    ]
    cur.executemany(
        f"INSERT OR REPLACE INTO {table} (chunk_id, text, meta_source, meta_file, meta_section, embedding) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    logger.info("Saved %d chunks to table '%s'", len(rows), table)


def load_chunks(conn: sqlite3.Connection, table: str) -> list[dict]:
    """Load all rows; embedding is deserialized from JSON."""
    import json
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {table}")
    rows = []
    for row in cur.fetchall():
        d = dict(row)
        if d["embedding"] is not None:
            d["embedding"] = json.loads(d["embedding"])
        rows.append(d)
    return rows
