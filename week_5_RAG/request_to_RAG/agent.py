"""RAG agent: toggle between plain LLM and retrieval-augmented answers."""

import logging

from generation import generate_answer
from retrieval import retrieve_chunks

logger = logging.getLogger(__name__)


def build_context(chunks: list[dict]) -> str:
    parts = []
    for c in chunks:
        parts.append(f"[{c['meta_section']}]\n{c['text']}")
    return "\n\n---\n\n".join(parts)


def ask_agent(question: str, use_rag: bool = True, strategy: str = "structural", top_k: int = 3) -> dict:
    """Answer `question`. If use_rag, retrieve chunks first and ground the answer in them.

    Returns {"answer": str, "sources": list[dict]} — sources empty when use_rag=False.
    """
    if not use_rag:
        logger.info("ask_agent: NO-RAG mode")
        answer = generate_answer(question, context=None)
        return {"answer": answer, "sources": []}

    logger.info("ask_agent: RAG mode (strategy=%s, top_k=%d)", strategy, top_k)
    chunks = retrieve_chunks(question, strategy=strategy, top_k=top_k)

    if not chunks:
        logger.warning("No chunks retrieved — falling back to context-free answer")
        answer = generate_answer(question, context=None)
        return {"answer": answer, "sources": []}

    context = build_context(chunks)
    answer = generate_answer(question, context=context)
    sources = [{"chunk_id": c["chunk_id"], "meta_section": c["meta_section"], "score": c["score"]} for c in chunks]
    return {"answer": answer, "sources": sources}
