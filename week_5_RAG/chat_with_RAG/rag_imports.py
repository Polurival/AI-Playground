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

# `request_to_RAG/generation.py` hard-exits at import time if DEEPSEEK_API_KEY is unset, and
# every reused module below (query_rewrite, generation_v3, agent_v2) imports from it. chat_with_RAG
# must still boot in a fully local run with no key at all — so seed a harmless placeholder before
# any of those imports run. `llm_provider.py` reads DEEPSEEK_KEY_PRESENT (the REAL value, captured
# here) to mark the "deepseek" provider unavailable rather than ever using the placeholder to call
# the real API.
DEEPSEEK_KEY_PRESENT = bool(os.environ.get("DEEPSEEK_API_KEY"))
if not DEEPSEEK_KEY_PRESENT:
    os.environ.setdefault("DEEPSEEK_API_KEY", "local-only-no-key-set")

# --- Step 1 of the pipeline: context-blind query rewrite (we feed it chat context ourselves) ---
from query_rewrite import rewrite_query, REWRITE_SYSTEM_PROMPT  # noqa: E402

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
    "REWRITE_SYSTEM_PROMPT",
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
    "DEEPSEEK_KEY_PRESENT",
]
