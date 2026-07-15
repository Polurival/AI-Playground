"""CPU sentence-transformers embeddings — no server, no Ollama, so it runs unchanged in any CI.

A symmetric model (default ``all-MiniLM-L6-v2``, ~80 MB) is used for both corpus chunks and
queries, so no asymmetric doc/query task prefixes are needed. The model is loaded once and cached.
"""

import logging

logger = logging.getLogger(__name__)

_model = None
_model_name = None


def _get_model(name: str):
    global _model, _model_name
    if _model is None or _model_name != name:
        from sentence_transformers import SentenceTransformer  # lazy: heavy import
        logger.info("[EMBED] loading model %s (CPU)", name)
        _model = SentenceTransformer(name, device="cpu")
        _model_name = name
    return _model


def embed_texts(texts: list[str], model_name: str, batch_size: int = 32) -> list[list[float]]:
    """Embed a batch of texts. Returns one vector (list[float]) per input."""
    if not texts:
        return []
    model = _get_model(model_name)
    vecs = model.encode(
        texts,
        batch_size=batch_size,
        convert_to_numpy=True,
        normalize_embeddings=True,     # unit vectors -> cosine == dot product
        show_progress_bar=False,
    )
    return [v.tolist() for v in vecs]


def embed_query(text: str, model_name: str) -> list[float]:
    return embed_texts([text], model_name)[0]
