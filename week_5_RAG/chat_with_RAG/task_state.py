"""Step 1 — Task memory (TaskState).

A small structure, separate from the raw message history, that survives even when the
chat window slides past the earliest turns. It is refreshed by a *light* LLM call before
every main DeepSeek request, so the agent keeps the dialogue's goals, constraints and
clarifications even after 12+ messages.

Fields:
- goals                : what the user is currently trying to find out.
- constraints_and_terms: fixed terms / entities / restrictions ("only ask about the Hatter",
                         "'the accused' means the Knave of Hearts", "do not mention the Queen").
- user_clarifications  : things the user has already pinned down during the conversation.
"""

import json
import logging
import re
from dataclasses import dataclass, field, asdict

from rag_imports import client, MODEL

logger = logging.getLogger(__name__)

# keep each list bounded so the state stays compact and cheap to inject every turn
_MAX_ITEMS_PER_LIST = 8


@dataclass
class TaskState:
    goals: list = field(default_factory=list)
    constraints_and_terms: list = field(default_factory=list)
    user_clarifications: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TaskState":
        return cls(
            goals=list(data.get("goals", [])),
            constraints_and_terms=list(data.get("constraints_and_terms", [])),
            user_clarifications=list(data.get("user_clarifications", [])),
        )

    def is_empty(self) -> bool:
        return not (self.goals or self.constraints_and_terms or self.user_clarifications)

    def to_prompt_block(self) -> str:
        """Render the state as a system-prompt block the model must respect each turn."""
        if self.is_empty():
            return "[TASK STATE] (empty so far — this is the start of the conversation)"

        lines = ["[TASK STATE — carry this across the whole conversation, honour it every turn]"]

        lines.append("Goals (what the user is trying to find out):")
        lines += [f"  - {g}" for g in self.goals] or ["  - (none yet)"]

        lines.append("Active constraints & fixed terms (MUST be obeyed strictly):")
        lines += [f"  - {c}" for c in self.constraints_and_terms] or ["  - (none yet)"]

        lines.append("User clarifications so far:")
        lines += [f"  - {u}" for u in self.user_clarifications] or ["  - (none yet)"]

        return "\n".join(lines)

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str) -> "TaskState":
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))


_STATE_UPDATER_SYSTEM_PROMPT = (
    "You maintain a compact TASK STATE for an ongoing chat about Lewis Carroll's \"Alice's "
    "Adventures in Wonderland\". You are given the CURRENT state (JSON) and the user's NEW "
    "message. Return the UPDATED state as JSON with exactly these three keys, each a list of "
    "short English strings:\n"
    "- \"goals\": the user's objectives. The FIRST item is the OVERARCHING goal for the whole "
    "conversation — the user's broad objective, usually set in their opening message and often "
    "signalled by phrases like 'I want to learn everything about X' or \"let's work through Y\". "
    "Capture it in the user's own broad terms (e.g. 'Learn everything about the Cheshire Cat', "
    "not just the first sub-question). ALWAYS keep this overarching goal as the first item on "
    "every update — never replace, narrow, or drop it unless the user clearly abandons the whole "
    "topic and starts an entirely different one. After it, list 1-4 current sub-goals for the "
    "present focus. 'Switch focus', 'now let's discuss X', 'remind me', and 'summarize' do NOT "
    "remove the overarching goal — a summary or reminder request still serves it. NEVER return "
    "an empty goals list.\n"
    "- \"constraints_and_terms\": restrictions and fixed definitions the user has set (e.g. "
    "'do not mention the Queen', \"'the accused' = the Knave of Hearts\"). NEVER drop a "
    "constraint unless the user explicitly lifts it — constraints are sticky.\n"
    "- \"user_clarifications\": facts/preferences the user has pinned down during the chat.\n\n"
    "Rules: merge, do not duplicate; keep each string short; keep each list to at most 8 items "
    "(keep the overarching goal + the most important/recent). Output ONLY the JSON object."
)


def _extract_json(text: str) -> dict:
    """Best-effort parse of a JSON object out of the model's reply (handles ``` fences)."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def update_task_state(state: TaskState, user_message: str) -> TaskState:
    """Light LLM call: fold the new user message into the running TaskState.

    Runs BEFORE the main RAG/DeepSeek answer call each turn (Step 1 requirement). On any
    failure it logs and returns the previous state unchanged, so the chat never breaks just
    because the state-updater hiccuped.
    """
    payload = (
        f"CURRENT STATE:\n{json.dumps(state.to_dict(), ensure_ascii=False)}\n\n"
        f"NEW USER MESSAGE:\n{user_message}"
    )
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": _STATE_UPDATER_SYSTEM_PROMPT},
                {"role": "user", "content": payload},
            ],
            max_tokens=400,
            temperature=0.0,
        )
        raw = response.choices[0].message.content or ""
        data = _extract_json(raw)
        new_state = TaskState.from_dict(data)
        # Defensive: never let the sticky memory forget an established goal or drop a constraint,
        # even if the model returns an empty/shrunken list on a "summarize"/"remind me" turn.
        if not new_state.goals and state.goals:
            new_state.goals = list(state.goals)
        for c in state.constraints_and_terms:
            if c not in new_state.constraints_and_terms:
                new_state.constraints_and_terms.append(c)
        # enforce the size cap defensively (don't trust the model to always obey)
        new_state.goals = new_state.goals[:_MAX_ITEMS_PER_LIST]
        new_state.constraints_and_terms = new_state.constraints_and_terms[:_MAX_ITEMS_PER_LIST]
        new_state.user_clarifications = new_state.user_clarifications[:_MAX_ITEMS_PER_LIST]
    except Exception as exc:  # noqa: BLE001 — never let state upkeep crash the chat
        logger.warning("[STATE] update failed (%s) — keeping previous state", exc)
        return state

    logger.info(
        "[STATE] updated -> goals=%d, constraints/terms=%d, clarifications=%d",
        len(new_state.goals), len(new_state.constraints_and_terms), len(new_state.user_clarifications),
    )
    if new_state.goals:
        logger.info("[STATE] current goal(s): %s", "; ".join(new_state.goals))
    if new_state.constraints_and_terms:
        logger.info("[STATE] active constraints/terms: %s", "; ".join(new_state.constraints_and_terms))
    return new_state
