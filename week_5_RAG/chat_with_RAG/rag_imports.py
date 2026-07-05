"""Single reuse hub: wires up sys.path and re-exports everything the chat needs from the
already-built RAG pipeline in `week_5_RAG/reranking_and_rewrite` (which in turn reuses
`week_5_RAG/request_to_RAG`). Nothing in the RAG engine is re-implemented here — the chat
just imports and orchestrates it."""

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_WEEK_5_DIR = os.path.dirname(_THIS_DIR)
_RERANK_DIR = os.path.join(_WEEK_5_DIR, "reranking_and_rewrite")
_REQUEST_DIR = os.path.join(_WEEK_5_DIR, "request_to_RAG")

# reranking_and_rewrite first so its modules shadow-nothing; request_to_RAG for client/MODEL.
for _d in (_RERANK_DIR, _REQUEST_DIR):
    if _d not in sys.path:
        sys.path.insert(0, _d)

# --- Step 1 of the pipeline: context-blind query rewrite (we feed it chat context ourselves) ---
from query_rewrite import rewrite_query  # noqa: E402

# --- Step 2: broad recall (top-10, cosine) + HARD relevance threshold + cross-encoder rerank ---
from retrieval_v2 import retrieve_chunks_advanced, SIMILARITY_THRESHOLD  # noqa: E402

# --- Step 3/4: structured-answer building blocks (## Answer / ## Quotes Used / ## Sources) ---
from generation_v3 import (  # noqa: E402
    build_context_v3,
    STRUCTURED_RAG_SYSTEM_PROMPT,
    ANSWER_HEADING,
    QUOTES_HEADING,
    SOURCES_HEADING,
)

# --- Canned "I don't know" answer used when the hard threshold fails ---
from agent_v2 import HARD_REFUSAL_ANSWER  # noqa: E402

# --- Raw DeepSeek client + model id (OpenAI-compatible), shared across the whole project ---
from generation import client, MODEL  # noqa: E402

__all__ = [
    "rewrite_query",
    "retrieve_chunks_advanced",
    "SIMILARITY_THRESHOLD",
    "build_context_v3",
    "STRUCTURED_RAG_SYSTEM_PROMPT",
    "ANSWER_HEADING",
    "QUOTES_HEADING",
    "SOURCES_HEADING",
    "HARD_REFUSAL_ANSWER",
    "client",
    "MODEL",
]
