"""Ollama embedding via nomic-embed-text (768-dim). Graceful fallback when Ollama offline."""

import json
import logging
import requests

OLLAMA_URL = "http://localhost:11434/api/embeddings"
MODEL = "nomic-embed-text"
EMBEDDING_DIM = 768

logger = logging.getLogger(__name__)


def get_embedding(text: str) -> list[float] | None:
    """Return 768-dim embedding or None if Ollama unavailable."""
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": MODEL, "prompt": text},
            timeout=30,
        )
        resp.raise_for_status()
        embedding = resp.json()["embedding"]
        return embedding
    except requests.exceptions.ConnectionError:
        logger.warning("Ollama not running at %s — embedding skipped", OLLAMA_URL)
        return None
    except requests.exceptions.Timeout:
        logger.warning("Ollama request timed out — embedding skipped")
        return None
    except Exception as exc:
        logger.warning("Embedding error: %s — embedding skipped", exc)
        return None


def embed_chunks(chunks: list[dict], label: str = "") -> list[dict]:
    """Add 'embedding' key (JSON string) to each chunk dict. None stored as null."""
    total = len(chunks)
    for i, chunk in enumerate(chunks, 1):
        if i % 10 == 0 or i == 1:
            logger.info("[%s] embedding %d/%d", label, i, total)
        vec = get_embedding(chunk["text"])
        chunk["embedding"] = json.dumps(vec)
    return chunks
