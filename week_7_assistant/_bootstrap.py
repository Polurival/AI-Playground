"""Wire sys.path so week_7 can reuse the already-built engines from earlier weeks instead of
re-implementing them:

- week_5_RAG                       -> database, embedder, chunkers (SQLite chunk store + Ollama embeddings)
- week_5_RAG/request_to_RAG        -> retrieval.cosine_similarity, generation.client/MODEL
- week_5_RAG/reranking_and_rewrite -> retrieval_v2.rerank_with_cross_encoder (cross-encoder rerank)
- week_5_RAG/chat_with_RAG         -> llm_provider (DeepSeek/Ollama switch, chat_completion)
- week_4_mcp/day_17_create_mcp     -> git_mcp_client.call_git_tool (own git MCP server over stdio)

Import this module FIRST in every week_7 entry point. It has no side effects beyond appending
to sys.path (idempotent)."""

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_THIS_DIR)

_REUSE_DIRS = [
    os.path.join(_ROOT, "week_5_RAG"),
    os.path.join(_ROOT, "week_5_RAG", "request_to_RAG"),
    os.path.join(_ROOT, "week_5_RAG", "reranking_and_rewrite"),
    os.path.join(_ROOT, "week_5_RAG", "chat_with_RAG"),
    os.path.join(_ROOT, "week_4_mcp", "day_17_create_mcp"),
]

for _d in _REUSE_DIRS:
    if _d not in sys.path:
        sys.path.insert(0, _d)
