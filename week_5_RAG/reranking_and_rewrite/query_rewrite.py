"""Query Rewrite: DeepSeek cleans up the user's question before it hits the embedder."""

import logging
import os
import sys

_REQUEST_TO_RAG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "request_to_RAG")
if _REQUEST_TO_RAG_DIR not in sys.path:
    sys.path.insert(0, _REQUEST_TO_RAG_DIR)

from generation import client, MODEL  # noqa: E402 — reused DeepSeek client from Task 2

logger = logging.getLogger(__name__)

REWRITE_SYSTEM_PROMPT = (
    "You rewrite user questions about Lewis Carroll's \"Alice's Adventures in Wonderland\" "
    "so they work as well as possible as a query for vector/semantic search over the book's text.\n\n"
    "Rules:\n"
    "- Resolve pronouns and vague references into explicit named entities from the book "
    "(e.g. 'he'/'it' -> 'the Caterpillar', 'the cat', 'the Knave of Hearts').\n"
    "- Fix obvious typos or garbled character/place names.\n"
    "- Make the query dense with the key nouns/entities it is actually about (character names, "
    "objects, chapter events) — drop filler words that don't help semantic search.\n"
    "- Keep the same language as the input question.\n"
    "- Keep it a single question, not a list, not an answer.\n"
    "- If the query is already clear and well-formed, return it UNCHANGED.\n"
    "- Output ONLY the rewritten query text — no quotes, no explanations, no preamble."
)


def rewrite_query(user_query: str) -> str:
    """Return a search-optimized rewrite of `user_query`, or the original if already good."""
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
            {"role": "user", "content": user_query},
        ],
        max_tokens=200,
        temperature=0.0,
    )
    rewritten = (response.choices[0].message.content or "").strip().strip('"')

    if not rewritten:
        logger.warning("Query rewrite returned empty output, falling back to original query")
        return user_query

    if rewritten != user_query:
        logger.info("[REWRITE] %r -> %r", user_query, rewritten)
    else:
        logger.info("[REWRITE] query already optimal, unchanged")

    return rewritten
