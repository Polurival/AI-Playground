"""Tiny self-contained SQLite vector store for the corpus.

Kept standalone (rather than reusing the week_5 store) so this package drops into any repo with no
cross-week imports. Embeddings are stored as JSON text; the corpus is small enough that a linear
cosine scan at query time is instant.
"""

import json
import sqlite3

_CREATE = """
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id  TEXT PRIMARY KEY,
    text      TEXT NOT NULL,
    file      TEXT NOT NULL,
    section   TEXT,
    embedding TEXT
)
"""


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(_CREATE)
    conn.commit()
    return conn


def replace_all(conn: sqlite3.Connection, chunks: list[dict]) -> None:
    """Overwrite the index with a fresh set of chunks (each must carry an ``embedding`` list)."""
    conn.execute("DELETE FROM chunks")
    conn.executemany(
        "INSERT OR REPLACE INTO chunks (chunk_id, text, file, section, embedding) VALUES (?,?,?,?,?)",
        [
            (c["chunk_id"], c["text"], c["file"], c.get("section", ""), json.dumps(c["embedding"]))
            for c in chunks
        ],
    )
    conn.commit()


def load_all(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT chunk_id, text, file, section, embedding FROM chunks").fetchall()
    out = []
    for r in rows:
        emb = json.loads(r["embedding"]) if r["embedding"] else None
        out.append({"chunk_id": r["chunk_id"], "text": r["text"], "file": r["file"],
                    "section": r["section"], "embedding": emb})
    return out


def count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
