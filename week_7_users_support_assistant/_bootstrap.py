"""Wire sys.path so this week_7 support assistant can reuse the engines already built in
earlier weeks instead of re-implementing them:

- week_5_RAG                       -> database (SQLite chunk store), embedder (Ollama embeddings)
- week_5_RAG/request_to_RAG        -> retrieval.cosine_similarity
- week_5_RAG/reranking_and_rewrite -> retrieval_v2.rerank_with_cross_encoder
- week_5_RAG/chat_with_RAG         -> llm_provider (DeepSeek/Ollama switch, chat_completion)

Unlike `week_7_assistant`, no MCP module is imported from week_4: the MCP server here is our own
(`crm_mcp_server.py`, CRM over JSON). Only the *shape* of week_4's git server/client is reused.

Import this module FIRST in every entry point. It has no side effects beyond appending to
sys.path (idempotent).
"""

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_THIS_DIR)

_REUSE_DIRS = [
    os.path.join(_ROOT, "week_5_RAG"),
    os.path.join(_ROOT, "week_5_RAG", "request_to_RAG"),
    os.path.join(_ROOT, "week_5_RAG", "reranking_and_rewrite"),
    os.path.join(_ROOT, "week_5_RAG", "chat_with_RAG"),
]

for _d in _REUSE_DIRS:
    if _d not in sys.path:
        sys.path.insert(0, _d)
