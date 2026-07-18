"""Wire sys.path so this package can reuse the already-built LLM backend from week_5 instead of
re-implementing it:

- week_5_RAG/chat_with_RAG -> llm_provider (chat_completion; DeepSeek client, OpenAI-compatible)

`llm_provider` pulls the rest of what it needs (the DeepSeek client + model id) through its own
`rag_imports` hub, so only the chat_with_RAG directory has to be on the path here.

Import this module FIRST in every entry point. No side effects beyond appending to sys.path
(idempotent)."""

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_THIS_DIR)

_REUSE_DIRS = [
    os.path.join(_ROOT, "week_5_RAG", "chat_with_RAG"),
]

for _d in _REUSE_DIRS:
    if _d not in sys.path:
        sys.path.insert(0, _d)
