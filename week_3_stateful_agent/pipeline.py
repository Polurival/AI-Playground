"""
Multi-agent task pipeline: planning -> execution -> validation (loop) -> done.

Unlike agent.py's single-agent state machine (one DeepSeekAgent transitions through all
states, carrying the full dialogue), this pipeline spawns a BRAND-NEW DeepSeekAgent per
stage — own memory_dir, own short-term history, starting empty. Only explicit handoff data
(plan text, structure text, invariants, validation report) crosses stage boundaries; the raw
conversation from one stage is never visible to the next stage's agent.
"""

import re
import time
from typing import Optional, Tuple, Dict, Any, List

from agent import DeepSeekAgent, ALLOWED_TRANSITIONS, DEFAULT_BACKEND

PLANNING_STAGE_PROMPT = """You are the PLANNING-stage agent of a multi-agent task pipeline.
You only ever operate in this one stage. A separate, freshly-created agent will handle
execution later, fed only by the plan you hand off — it will not see this conversation.

Task: {task_description}

Step 0 — Invariants: If the [HARD INVARIANTS] system block is EMPTY or absent, before proposing
anything ask the user: "What invariants/constraints must never be violated? (architecture, tech
stack limits, business rules)". If invariants already exist, restate them and design around
every one of them.

Persisting invariants: whenever the user gives or changes invariants, end that same response
with the full current list wrapped exactly like this:
[INVARIANTS_SET]
first invariant
second invariant
[/INVARIANTS_SET]
("none" -> empty block: [INVARIANTS_SET][/INVARIANTS_SET])

Plan output structure:
1. Processes/Features
2. Design & UI/UX
3. Tech Stack
4. Architecture (components, modules, relationships)
5. Database schema (if needed)

When the user confirms the plan is complete ("ready to execute"), restate the FULL final plan
one more time in that reply — the orchestrator captures your last message verbatim as the plan
handed to the execution agent.
"""

EXECUTION_STAGE_PROMPT = """You are the EXECUTION-stage agent of a multi-agent task pipeline.
You were just created fresh — you have NOT seen the planning conversation. The only context
you get is below: the task, the approved plan, and (if this is a correction round) the issues
the validation agent found. Treat the plan as ground truth; do not re-litigate it.

Task: {task_description}

Propose an implementation structure:
- Directory tree
- File list with brief descriptions
- Key files with pseudo-code/structure outline
- Dependencies & imports

Check every part against [HARD INVARIANTS] if present. If a natural choice would violate one,
refuse that part, name the invariant, explain why, and propose a compliant alternative.

If this is a correction round, show a `[EXECUTION: corrections]` header, list each issue you are
fixing (tag invariant violations as "(invariant violation)"), and map each fix back to its issue.
"""

VALIDATION_STAGE_PROMPT = """You are the VALIDATION-stage agent of a multi-agent task pipeline.
You were just created fresh — you have NOT seen the planning or execution conversations. The
only context you get is the plan and the proposed structure below, plus [HARD INVARIANTS] if
present.

Task: {task_description}

Cross-check the structure against the plan:
1. Does each plan point map to the implementation?
2. Are all features covered?
3. Is the architecture followed?
4. Any conflicts or gaps?
5. Does any part conflict with any [HARD INVARIANTS] item? Check each one by one.

Output a validation checklist with a dedicated "Invariants check" section (✓/✗ per invariant).

End your response with exactly these two machine-readable markers, each on its own line:
`[RESULT: VALID]` or `[RESULT: ISSUES]`
`[INVARIANTS: OK]` or `[INVARIANTS: VIOLATED]`
If ISSUES or VIOLATED, list every discrepancy/violation above those lines so the next execution
agent (fresh, fed only your issue list — not your full reasoning) can fix them.
"""

DONE_STAGE_PROMPT = """You are the DONE-stage agent of a multi-agent task pipeline.
You were just created fresh — you have NOT seen any prior conversation. The only context you
get is the final plan, structure, and validation report below.

Task: {task_description}

Summarize:
1. Completed checklist
2. What was accomplished
3. Potential improvements/extensions
4. Next steps if continued
"""


class TaskPipeline:
    """Orchestrates a task through planning -> execution -> validation (loop) -> done,
    handing off only structured results between a fresh agent per stage."""

    def __init__(
        self,
        task_description: str,
        memory_root: str = ".memory_pipeline",
        backend: str = DEFAULT_BACKEND,
    ):
        self.task_description = task_description
        self.memory_root = memory_root
        # Every stage agent this pipeline spawns uses this backend (deepseek/local).
        self.backend = backend
        self.run_id = str(int(time.time()))

        self.planning_agent: Optional[DeepSeekAgent] = None
        self.execution_agent: Optional[DeepSeekAgent] = None
        self.validation_agent: Optional[DeepSeekAgent] = None
        self.done_agent: Optional[DeepSeekAgent] = None

        self.invariants: List[str] = []
        self.plan_text: Optional[str] = None
        self.structure_text: Optional[str] = None
        self.validation_text: Optional[str] = None
        self.invariants_satisfied: Optional[bool] = None
        # True only while validation_text/invariants_satisfied above describe THIS exact
        # structure_text. Reset to False on every new run_execution() so a stale "passed"
        # verdict from a previous round can never carry over to a later, unvalidated structure.
        self.validation_passed: bool = False
        self.validation_round = 0
        # Bumped by reopen_planning() so a reopened run gets fresh memory dirs instead of
        # reloading (and silently inheriting) the original planning agent's saved history.
        self.epoch = 0
        self.stage = "idle"  # idle, planning, execution, validation, done

    def _require_transition(self, target: str) -> None:
        """Same ALLOWED_TRANSITIONS table agent.py's single-agent state machine uses — code
        enforced, refuses to skip/jump a stage regardless of what calls it (CLI, demo, bug)."""
        if target not in ALLOWED_TRANSITIONS.get(self.stage, set()):
            raise RuntimeError(
                f"Illegal pipeline transition {self.stage} -> {target}. "
                f"Allowed from '{self.stage}': {sorted(ALLOWED_TRANSITIONS.get(self.stage, set()))}"
            )

    def _stage_dir(self, stage: str) -> str:
        return f"{self.memory_root}_{self.run_id}_e{self.epoch}_{stage}_{self.validation_round}"

    def _new_agent(self, stage: str, system_prompt: str) -> DeepSeekAgent:
        """Always a fresh DeepSeekAgent: new memory_dir => empty short-term/working/long-term
        history. Invariants (the one thing that must survive across stages) are re-applied
        explicitly, not inherited from any prior agent's memory."""
        agent = DeepSeekAgent(
            use_state_machine=False,
            system_prompt=system_prompt,
            memory_dir=self._stage_dir(stage),
            backend=self.backend,
        )
        if self.invariants:
            agent.set_invariants(self.invariants)
        return agent

    # ---- PLANNING ----
    def start_planning(self) -> Tuple[str, Dict[str, Any]]:
        self._require_transition("planning")
        prompt = PLANNING_STAGE_PROMPT.format(task_description=self.task_description)
        self.planning_agent = self._new_agent("planning", prompt)
        self.stage = "planning"
        response, metrics = self.planning_agent.send_message(f"[TASK START]\n{self.task_description}")
        self._sync_invariants(response)
        return response, metrics

    def chat_planning(self, user_text: str) -> Tuple[str, Dict[str, Any]]:
        if self.stage != "planning" or self.planning_agent is None:
            raise RuntimeError(
                f"Cannot chat with the planning agent from stage '{self.stage}' "
                f"(planning is finalized/discarded, or never started)."
            )
        response, metrics = self.planning_agent.send_message(user_text)
        self._sync_invariants(response)
        return response, metrics

    def _sync_invariants(self, response: str) -> None:
        m = re.search(r"\[INVARIANTS_SET\](.*?)\[/INVARIANTS_SET\]", response, re.IGNORECASE | re.DOTALL)
        if not m:
            return
        raw = m.group(1).strip().splitlines()
        items = [re.sub(r"^[\-\*\d\.\)\s]+", "", line).strip() for line in raw]
        self.invariants = [i for i in items if i]

    def finalize_planning(self, plan_override: Optional[str] = None) -> None:
        """Capture the plan handoff, then DISCARD the planning agent — execution starts
        with a brand-new agent that never sees this dialogue. Does NOT advance self.stage:
        the planning -> execution transition is only granted by run_execution(), so a caller
        can't finalize and then stall in a half-transitioned state."""
        if self.stage != "planning":
            raise RuntimeError(f"Cannot finalize planning from stage '{self.stage}'.")
        last_plan = plan_override
        if last_plan is None and self.planning_agent is not None:
            msgs = self.planning_agent.memory.short_term.get_all_messages()
            assistant_msgs = [m for m in msgs if m["role"] == "assistant"]
            last_plan = assistant_msgs[-1]["content"] if assistant_msgs else ""
        self.plan_text = last_plan or ""
        if self.planning_agent is not None:
            self.invariants = self.planning_agent.get_invariants() or self.invariants
        self.planning_agent = None

    # ---- EXECUTION ----
    def run_execution(self, corrections: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
        # Reachable only from "planning" (first pass, plan must be finalized) or "validation"
        # (correction loop) — table-enforced, same as agent.py's single-agent guard.
        self._require_transition("execution")
        if self.plan_text is None:
            raise RuntimeError("Cannot run execution before planning is finalized (no approved plan).")
        prompt = EXECUTION_STAGE_PROMPT.format(task_description=self.task_description)
        self.execution_agent = self._new_agent("execution", prompt)
        handoff = f"Approved Plan:\n{self.plan_text}"
        if corrections:
            handoff += f"\n\nValidation found issues to fix:\n{corrections}"
        response, metrics = self.execution_agent.send_message(handoff)
        self.structure_text = response
        self.stage = "execution"
        # A fresh, unvalidated structure exists now — any prior "validated OK" verdict is stale.
        self.validation_passed = False
        self.invariants_satisfied = None
        return response, metrics

    # ---- VALIDATION ----
    def run_validation(self) -> Tuple[str, Dict[str, Any], bool]:
        # Reachable only from "execution" — table-enforced.
        self._require_transition("validation")
        if self.structure_text is None:
            raise RuntimeError("Cannot validate before execution has produced a structure.")
        prompt = VALIDATION_STAGE_PROMPT.format(task_description=self.task_description)
        self.validation_agent = self._new_agent("validation", prompt)
        handoff = f"Plan:\n{self.plan_text}\n\nProposed Structure:\n{self.structure_text}"
        response, metrics = self.validation_agent.send_message(handoff)
        self.validation_text = response
        self.stage = "validation"

        result_match = re.search(r"\[RESULT:\s*(VALID|ISSUES)\]", response, re.IGNORECASE)
        inv_match = re.search(r"\[INVARIANTS:\s*(OK|VIOLATED)\]", response, re.IGNORECASE)
        result_ok = bool(result_match) and result_match.group(1).upper() == "VALID"
        self.invariants_satisfied = (inv_match.group(1).upper() == "OK") if inv_match else None

        is_valid = result_ok and self.invariants_satisfied is True
        # This verdict is pinned to the structure_text validated just now — run_done() checks
        # this exact flag, and run_execution() above always resets it before producing a new
        # structure, so a stale pass from an earlier round can never leak forward.
        self.validation_passed = is_valid
        # Discard this round's execution agent — a correction round (if needed) starts with
        # a fresh agent fed the issue list, not a continuation of this one's history.
        self.execution_agent = None
        if not is_valid:
            self.validation_round += 1
        return response, metrics, is_valid

    # ---- DONE ----
    def run_done(self) -> Tuple[str, Dict[str, Any]]:
        # Reachable only from "validation" — table-enforced. This is what makes "no jumping
        # to done without finishing validation" a code guarantee, not a prompt instruction.
        self._require_transition("done")
        if not self.validation_passed:
            raise RuntimeError(
                "Cannot reach DONE: current structure has not passed validation "
                "(issues found, invariants violated, or never validated)."
            )
        prompt = DONE_STAGE_PROMPT.format(task_description=self.task_description)
        self.done_agent = self._new_agent("done", prompt)
        handoff = (
            f"Plan:\n{self.plan_text}\n\nFinal Structure:\n{self.structure_text}"
            f"\n\nValidation Report:\n{self.validation_text}"
        )
        response, metrics = self.done_agent.send_message(handoff)
        self.validation_agent = None
        self.stage = "done"
        return response, metrics

    # ---- REOPEN ----
    def reopen_planning(self, revision_request: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
        """User-initiated: go back to PLANNING to revise an already-finished task.
        Unlike a fresh start_planning(), the new planning agent IS handed the previous
        plan/structure/validation report as explicit handoff text (so it can actually revise
        the existing solution) — it just never sees the discarded raw dialogue from those
        stages. Invariants carry over unchanged (they're hard constraints for the whole task).
        Bumps epoch so memory dirs are fresh, not a reload of the original planning agent's
        saved history."""
        self._require_transition("planning")
        old_plan, old_structure, old_validation = self.plan_text, self.structure_text, self.validation_text

        self.epoch += 1
        self.validation_round = 0
        self.planning_agent = None
        self.execution_agent = None
        self.validation_agent = None
        self.done_agent = None
        self.plan_text = None
        self.structure_text = None
        self.validation_text = None
        self.validation_passed = False
        self.invariants_satisfied = None

        prompt = PLANNING_STAGE_PROMPT.format(task_description=self.task_description)
        self.planning_agent = self._new_agent("planning", prompt)
        self.stage = "planning"

        handoff = (
            f"[TASK REOPENED FOR REVISION]\n{self.task_description}\n\n"
            f"Previous plan:\n{old_plan}\n\n"
            f"Previous structure:\n{old_structure}\n\n"
            f"Previous validation report:\n{old_validation}\n"
        )
        if revision_request:
            handoff += f"\nRequested revision:\n{revision_request}\n"
        handoff += "\nRevise the plan above to address the requested changes; keep everything else intact."

        response, metrics = self.planning_agent.send_message(handoff)
        self._sync_invariants(response)
        return response, metrics

    def current_agent(self) -> Optional[DeepSeekAgent]:
        """The agent backing whichever stage is currently active (or just finished)."""
        return self.done_agent or self.validation_agent or self.execution_agent or self.planning_agent

    def status(self) -> Dict[str, Any]:
        return {
            "task_description": self.task_description,
            "stage": self.stage,
            "validation_round": self.validation_round,
            "invariants": list(self.invariants),
            "invariants_satisfied": self.invariants_satisfied,
            "has_plan": bool(self.plan_text),
            "has_structure": bool(self.structure_text),
            "has_validation": bool(self.validation_text),
        }
