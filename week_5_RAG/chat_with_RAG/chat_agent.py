"""Stateful chat orchestrator. Holds the message history + TaskState and, on every user turn,
runs the full pipeline:

    update TaskState (light LLM call)
      -> context-aware query rewrite (reuses rewrite_query, routed via llm_provider)
      -> broad retrieval + hard threshold + rerank (reuses retrieve_chunks_advanced, always local)
      -> [threshold failed?] canned refusal, NO main LLM call
      -> [else] structured chat answer with Context + Quotes + Sources + history + TaskState

The RAG engine itself is untouched — this class only sequences it and layers state on top.
Every LLM call (rewrite, TaskState update, final answer) goes through `llm_provider.py`, which
picks local (Ollama) vs DeepSeek (cloud) based on the currently active provider — see `/model`
in `main_chat.py`.
"""

import logging

from rag_imports import (
    retrieve_chunks_advanced,
    HARD_REFUSAL_ANSWER,
)
from chat_generation import generate_chat_answer
from task_state import TaskState, update_task_state
from llm_provider import rewrite_query_active as rewrite_query, current_label

logger = logging.getLogger(__name__)

# how many recent USER turns to fold into the query rewriter so follow-ups resolve correctly
_REWRITE_CONTEXT_TURNS = 4

# Chat uses a LOOSER hard floor than the one-shot QA eval (which used SIMILARITY_THRESHOLD=0.60).
# Why: conversational follow-ups are short ("and his grin?"), so their embeddings score lower
# even when perfectly on-topic — with nomic-embed-text, genuine in-book chat queries land around
# 0.53-0.60, overlapping the off-topic band. A 0.60 floor would refuse legitimate follow-ups.
# So in chat the hard floor is only a GARBAGE catcher (skip the API for truly unrelated input),
# and precise relevance is handled by two other layers that stay fully in force:
#   (1) the cross-encoder rerank picks the best 3 of whatever passes, and
#   (2) the structured prompt's soft-refusal ("Answer: not in the book" + "—" quotes/sources)
#       catches on-topic-looking queries whose chunks still don't contain the answer.
CHAT_SIMILARITY_THRESHOLD = 0.50


class ChatAgent:
    """One conversation. `messages` is the running history; `task_state` is the sticky memory."""

    def __init__(
        self,
        strategy: str = "structural",
        language: str | None = "English",
        similarity_threshold: float = CHAT_SIMILARITY_THRESHOLD,
    ):
        self.strategy = strategy
        self.language = language
        self.similarity_threshold = similarity_threshold
        self.messages: list[dict] = []       # [{role, content}, ...] — Step 1 message history
        self.task_state = TaskState()         # Step 1 task memory
        self._primary_goal: str | None = None  # overarching goal, pinned once and kept forever
        self.turn = 0

    # ------------------------------------------------------------------ helpers

    def _recent_user_turns(self) -> list[str]:
        users = [m["content"] for m in self.messages if m["role"] == "user"]
        return users[-_REWRITE_CONTEXT_TURNS:]

    def _contextualize(self, question: str) -> str:
        """Wrap the current question with recent user turns so `rewrite_query` can resolve
        pronouns/follow-ups ("his grin" -> "the Cheshire Cat's grin") from the conversation.
        When there is no prior context, pass the bare question through unchanged."""
        recent = self._recent_user_turns()
        if not recent:
            return question
        convo = "\n".join(f"- {t}" for t in recent)
        return (
            "Earlier user turns (most recent last), for reference only:\n"
            f"{convo}\n\n"
            f"Rewrite ONLY this current question into a standalone search query: {question}"
        )

    # ------------------------------------------------------------------ main entry

    def ask(self, user_text: str) -> dict:
        """Run one full turn. Returns a result dict with the answer, sources and diagnostics."""
        self.turn += 1
        logger.info("[CHAT] === turn %d === user: %s", self.turn, user_text)

        # Step 1 — refresh TaskState BEFORE any main DeepSeek call
        self.task_state = update_task_state(self.task_state, user_text)

        # Pin the overarching goal once (the first goal ever established) and guarantee it stays
        # first on every later turn — this is what makes the goal survive "switch focus" /
        # "summarize" turns and the sliding history window, deterministically (not just by prompt).
        if self._primary_goal is None and self.task_state.goals:
            self._primary_goal = self.task_state.goals[0]
        elif self._primary_goal and self._primary_goal not in self.task_state.goals:
            self.task_state.goals.insert(0, self._primary_goal)

        # Step 2.1 — context-aware rewrite (reused rewrite_query, fed chat context)
        rewritten = rewrite_query(self._contextualize(user_text))

        # Step 2.2 — retrieval + hard relevance threshold + rerank (reused)
        search = retrieve_chunks_advanced(
            rewritten, strategy=self.strategy, similarity_threshold=self.similarity_threshold
        )
        max_score = search["max_score"]
        threshold_passed = search["threshold_passed"]

        if not threshold_passed:
            logger.warning(
                "[REFUSAL] max cosine %.4f < %.2f — refusing, NO main LLM call this turn",
                max_score or 0.0, self.similarity_threshold,
            )
            answer = HARD_REFUSAL_ANSWER
            sources = []
            hard_refusal = True
            elapsed = None
        else:
            kept = search["kept"]
            # history passed to the model is everything BEFORE this turn's user message
            answer, elapsed = generate_chat_answer(
                self.messages, self.task_state, user_text, kept, language=self.language
            )
            sources = [
                {
                    "chunk_id": c["chunk_id"],
                    "meta_source": c["meta_source"],
                    "meta_section": c["meta_section"],
                    "score": c["score"],
                    "rerank_score": c.get("rerank_score"),
                }
                for c in kept
            ]
            hard_refusal = False

        # append this turn to the running history (plain user text + full structured answer)
        self.messages.append({"role": "user", "content": user_text})
        self.messages.append({"role": "assistant", "content": answer})

        return {
            "turn": self.turn,
            "question": user_text,
            "rewritten_query": rewritten,
            "answer": answer,
            "sources": sources,
            "max_score": max_score,
            "threshold_passed": threshold_passed,
            "hard_refusal": hard_refusal,
            "task_state": self.task_state.to_dict(),
            "provider": current_label(),
            "elapsed_s": elapsed,
        }
