"""Step 2 (part 3-4) — pack Context + Sources + Quotes + chat history + TaskState into the
prompt and get a structured answer that ALWAYS ends with the ## Quotes Used / ## Sources
blocks. Reuses the structured RAG system prompt and context builder from `generation_v3`."""

import logging

from rag_imports import (
    build_context_v3,
    STRUCTURED_RAG_SYSTEM_PROMPT,
    ANSWER_HEADING,
    QUOTES_HEADING,
    SOURCES_HEADING,
)
from llm_provider import timed_chat_completion, current_label
from task_state import TaskState

logger = logging.getLogger(__name__)

# how many of the most recent history messages to replay to the model. Deliberately small so
# that goal/constraint retention past this window has to come from TaskState, not raw history.
HISTORY_WINDOW = 8

_CHAT_ADDENDUM = (
    "\n\n--- CHAT MODE ---\n"
    "This is a multi-turn conversation. Earlier turns are provided as message history, and a "
    "TASK STATE block pins the running goals, fixed terms and constraints. You MUST:\n"
    "- Use the message history to resolve follow-up references (\"his grin\", \"that witness\", "
    "\"the accused\") to the right entity.\n"
    "- Honour fixed-term definitions (use the user's term with the meaning they assigned).\n"
    "- ALWAYS produce all three blocks in every answer, even for short follow-ups: "
    f"'{ANSWER_HEADING}', '{QUOTES_HEADING}', '{SOURCES_HEADING}'. Never skip the quotes or "
    "sources block.\n"
    "- Ground every answer ONLY in the freshly retrieved context for THIS turn; if that context "
    "does not contain the answer, say so in the Answer block and put \"—\" in the other two."
)


def _active_constraints_block(task_state: TaskState) -> str:
    """A high-salience, top-of-prompt block for constraints of the 'do NOT mention X' kind, so
    the model treats them as a hard ceiling even on scenes where the forbidden entity is central."""
    if not task_state.constraints_and_terms:
        return ""
    lines = [
        "!!! ABSOLUTE CONSTRAINTS — HIGHEST PRIORITY, OVERRIDE EVERYTHING ELSE !!!",
        "The user has set these hard rules for the whole conversation. Obeying them outranks "
        "completeness and outranks the retrieved context. If a rule forbids mentioning an entity, "
        "that word must NOT appear in the Answer text or in any quote you choose — EVEN IF the "
        "scene is centred on that entity and the retrieved context is full of it. When a scene "
        "involves the forbidden entity as a participant, name only the OTHER participants and "
        "describe the forbidden entity's role obliquely ('the ruler', 'someone', 'a bystander') "
        "or omit it entirely — never list it by name among the participants. It is better to give a "
        "partial answer than to break a rule. If a needed quote contains the forbidden word, pick "
        "a different quote or omit that quote. (This rule governs the Answer and Quotes; the "
        "Sources block may still cite the immutable chapter title as provenance.)",
    ]
    for c in task_state.constraints_and_terms:
        lines.append(f"  - {c}")
    return "\n".join(lines)


def build_chat_system_prompt(task_state: TaskState, language: str | None = None) -> str:
    """Structured RAG prompt + chat rules + current TaskState (+ optional forced language).

    Active constraints are placed FIRST (before the structured-format rules) for maximum salience,
    then repeated inside the TaskState block, so 'do not mention X' rules are hard to ignore."""
    parts = []
    constraints_block = _active_constraints_block(task_state)
    if constraints_block:
        parts.append(constraints_block)
    parts += [STRUCTURED_RAG_SYSTEM_PROMPT, _CHAT_ADDENDUM, task_state.to_prompt_block()]
    if language:
        parts.append(
            f"Always write the body of '{ANSWER_HEADING}' in {language}, regardless of the "
            "language of the question or context; keep the three headings exactly as specified "
            "and keep quotes verbatim in their original language."
        )
    return "\n\n".join(parts)


def _trim_history(messages: list[dict], window: int = HISTORY_WINDOW) -> list[dict]:
    return messages[-window:] if len(messages) > window else messages


def generate_chat_answer(
    prior_messages: list[dict],
    task_state: TaskState,
    question: str,
    chunks: list[dict],
    language: str | None = None,
) -> tuple[str, float]:
    """Assemble [system(structured+state)] + [trimmed history] + [context+question] and call
    whichever LLM provider (local or DeepSeek) is currently active (see `llm_provider.py`).
    `prior_messages` is the history BEFORE this turn's user message. Returns
    (structured Markdown answer, wall-clock seconds spent in the generation call)."""
    system_prompt = build_chat_system_prompt(task_state, language)
    context = build_context_v3(chunks)

    history = _trim_history(prior_messages)
    final_user = f"Context (retrieved for THIS question):\n{context}\n\nQuestion: {question}"

    api_messages = [{"role": "system", "content": system_prompt}]
    api_messages += history
    api_messages.append({"role": "user", "content": final_user})

    logger.info(
        "[CHAT] generating answer via %s -> %d context chunk(s), %d history msg(s) in window, language=%s",
        current_label(), len(chunks), len(history), language or "auto",
    )

    answer, elapsed = timed_chat_completion(api_messages, max_tokens=1000, temperature=0.2)

    has_quotes = QUOTES_HEADING in answer
    has_sources = SOURCES_HEADING in answer
    logger.info(
        "[CHAT] answer received in %.2fs (%d chars) — blocks present: Answer=%s, Quotes=%s, Sources=%s",
        elapsed, len(answer), ANSWER_HEADING in answer, has_quotes, has_sources,
    )
    if not (has_quotes and has_sources):
        logger.warning("[CHAT] answer is MISSING a required block (quotes=%s, sources=%s)", has_quotes, has_sources)
    return answer, elapsed
