"""Structured RAG generation (Task 4): forces the model into a strict Markdown answer shape
with `## Answer` / `## Quotes Used` / `## Sources` blocks, so every answer is traceable back
to exact chunks and quotes instead of a free-form paragraph."""

import logging
import os
import sys

_REQUEST_TO_RAG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "request_to_RAG")
if _REQUEST_TO_RAG_DIR not in sys.path:
    sys.path.insert(0, _REQUEST_TO_RAG_DIR)

from generation import client, MODEL  # noqa: E402 — reused DeepSeek client from Task 2

logger = logging.getLogger(__name__)

ANSWER_HEADING = "## Answer"
QUOTES_HEADING = "## Quotes Used"
SOURCES_HEADING = "## Sources"

STRUCTURED_RAG_SYSTEM_PROMPT = (
    "You are a strict-factual-accuracy assistant for Lewis Carroll's \"Alice's Adventures in "
    "Wonderland\". Answer ONLY based on the context provided below. Never invent facts that "
    "are not in the context.\n\n"
    "Each context fragment is tagged like this:\n"
    "[chunk_id: ... | source: ... | section: ...]\n"
    "<fragment text>\n\n"
    "Your answer MUST be in the following strict Markdown format, with these three headings "
    "in exactly this order and exactly as written:\n\n"
    f"{ANSWER_HEADING}\n"
    "A short, precise answer to the user's question (1-3 sentences), based EXCLUSIVELY on the "
    "provided context.\n\n"
    f"{QUOTES_HEADING}\n"
    "Direct verbatim excerpts from the context (in quotation marks) that the answer is based "
    "on. Each quote is its own bullet point (\"- \"), copied verbatim, never paraphrased.\n\n"
    f"{SOURCES_HEADING}\n"
    "The list of fragments used, one bullet point each, strictly in this format:\n"
    "- source: <meta_source> | section: <meta_section> | chunk_id: <chunk_id>\n\n"
    "If the context does not contain the answer to the question, say so honestly in the "
    f"\"{ANSWER_HEADING}\" section, and write \"—\" in the \"{QUOTES_HEADING}\" and "
    f"\"{SOURCES_HEADING}\" sections. Never invent facts and never make up sources."
)


def build_context_v3(chunks: list[dict]) -> str:
    """Context with explicit chunk_id/source/section tags so the model can cite them exactly."""
    parts = []
    for c in chunks:
        header = f"[chunk_id: {c['chunk_id']} | source: {c.get('meta_source', '')} | section: {c['meta_section']}]"
        parts.append(f"{header}\n{c['text']}")
    return "\n\n---\n\n".join(parts)


def generate_structured_answer(question: str, chunks: list[dict], language: str | None = None) -> str:
    """Call DeepSeek with the structured RAG prompt. Returns Markdown text containing the
    Answer / Quotes Used / Sources blocks."""
    context = build_context_v3(chunks)
    system_prompt = STRUCTURED_RAG_SYSTEM_PROMPT
    if language:
        system_prompt = f"{system_prompt} Always answer in {language}, regardless of the language of the question or context."

    user_content = f"Context:\n{context}\n\nQuestion: {question}"

    logger.info(
        "[GENERATE-v3] structured call -> %d context chunk(s), language=%s",
        len(chunks), language or "auto",
    )

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        max_tokens=1000,
        temperature=0.2,
    )
    answer = response.choices[0].message.content or ""

    has_answer = ANSWER_HEADING in answer
    has_quotes = QUOTES_HEADING in answer
    has_sources = SOURCES_HEADING in answer
    logger.info(
        "[GENERATE-v3] structured answer received (%d chars) — blocks present: Answer=%s, Quotes=%s, Sources=%s",
        len(answer), has_answer, has_quotes, has_sources,
    )
    return answer
