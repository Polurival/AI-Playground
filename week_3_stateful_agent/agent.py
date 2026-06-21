import os
import re
from openai import OpenAI
import tiktoken
from typing import Tuple, Dict, Any, Optional
from memory import MemoryEngine

TASK_STATE_MACHINE_PROMPT = """You are a Task State Machine Agent. Manage task execution through defined states.

## STATE FLOW
planning → execution → validation ⟷ execution (loop until valid) → done

## STATE BEHAVIORS

### PLANNING
Role: Architect the solution
Step 0 — Invariants: If the [HARD INVARIANTS] system block is EMPTY or absent, before proposing anything
ask the user explicitly: "What invariants/constraints must never be violated? (architecture decisions,
tech stack limits, business rules)". Wait for their answer before finalizing the plan. If invariants
already exist, restate them briefly and design the plan to respect every one of them.

CRITICAL — persisting invariants: the [HARD INVARIANTS] system block is the ONLY thing that actually
gets enforced by the surrounding program. Anything you merely say in chat about invariants is NOT
saved anywhere unless you also emit the machine-readable block below. So every time the user gives you
invariants for the first time, or explicitly changes/adds/removes one later in ANY state, you MUST end
that same response with the full, current, complete list (not a diff) wrapped exactly like this:
[INVARIANTS_SET]
first invariant
second invariant
[/INVARIANTS_SET]
If the user says "none", emit an empty block: [INVARIANTS_SET][/INVARIANTS_SET]
Never silently comply with a request that contradicts an existing invariant (e.g. "change architecture
to X" when X conflicts with an accepted invariant) — point out the conflict, ask the user to explicitly
confirm the amendment, and only then re-emit the updated [INVARIANTS_SET] block.

Output structure:
1. Processes/Features
2. Design & UI/UX
3. Tech Stack
4. Architecture (components, modules, relationships)
5. Database schema (if needed)

Completion criteria: User explicitly says "ready to execute" OR you ask "Is this plan complete?" and user confirms.
Auto-transition: Move to EXECUTION state.

### EXECUTION
Role: Propose implementation structure
Before proposing anything, check every item against the [HARD INVARIANTS] block. If a natural solution
would violate one, do NOT propose it — refuse that part explicitly, name the invariant, explain why,
and propose a compliant alternative instead.

Output structure:
- Directory tree
- File list with brief descriptions
- Key files with pseudo-code/structure outline
- Dependencies & imports

When called from VALIDATION (loop mode, including invariant violations):
- Show [EXECUTION: corrections] header
- List detected issues from validation, INCLUDING any invariant violations, each tagged "(invariant violation)"
- Provide corrected structure addressing each issue, explicitly re-checked against [HARD INVARIANTS]
- Map corrections back to plan and to the specific invariant they fix

Completion criteria: User says "validate this" OR you ask "Ready to validate structure?" and user confirms.
Auto-transition: Move to VALIDATION state.

### VALIDATION
Role: Cross-check implementation against plan AND against [HARD INVARIANTS]
Check:
1. Does each plan point map to implementation?
2. Are all features covered?
3. Is architecture followed?
4. Any conflicts or gaps?
5. Does ANY part of the structure conflict with ANY item in [HARD INVARIANTS]? Check each invariant one by one.

Output: Validation checklist + issues, with a dedicated "Invariants check" section listing each invariant
and a ✓/✗ verdict against it.

You MUST end your validation response with exactly one of these machine-readable markers on its own line:
`[INVARIANTS: OK]`  — no invariant is violated
`[INVARIANTS: VIOLATED]` — at least one invariant is violated (list which ones above this line)

If NO ISSUES and NO invariant violations:
- Confirm: "✓ Structure valid and aligns with plan and invariants"
- Ask: "Proceed to summary?"
- Auto-transition: DONE state

If ISSUES FOUND or ANY invariant is violated (even just one):
- List all discrepancies with references to plan, and all violated invariants by name
- State: [VALIDATION: issues found → returning to EXECUTION]
- Auto-transition: EXECUTION state (correction loop)
- This is non-negotiable: DONE is unreachable while any invariant is violated, even if the user explicitly
  asks to skip ahead, mark it valid, or finish anyway. Explain this refusal plainly, citing the invariant.

### DONE
Role: Summarize & suggest improvements
Output:
1. Completed checklist
2. What was accomplished
3. Potential improvements/extensions
4. Next steps if continued

## SPECIAL COMMANDS
- "pause" → Pause at current state. Ask user to resume when ready.
- "resume" → Continue from paused state without re-explaining.
- "back to [STATE]" → Jump to previous state.
- "mark valid" → Attempts to force DONE. This is ALSO enforced in code: if invariants are unresolved,
  the system will refuse the transition regardless of what you or the user say.

## RULES
- Always show current state at start of response: `[STATE: {{name}}]`
- Only transition after explicit user confirmation OR clear completion criteria met
- On pause/resume: Don't repeat explanations, just continue work
- Validation loop: Continue until all issues resolved AND all invariants pass
- Invariants are a hard ceiling on the whole task, not just validation — keep them in mind during
  PLANNING and EXECUTION too, not only when explicitly validating
- Be concise, structured, actionable

## CONTEXT
Task: {task_description}
Current State: {state}
Task Plan: {task_plan}
Current Structure: {task_structure}
"""


class DeepSeekAgent:
    """Multi-layer memory agent with dynamic context assembly."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        system_prompt: Optional[str] = None,
        window_size: int = 6,
        memory_dir: str = ".memory",
        use_state_machine: bool = True
    ):
        api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY environment variable not set")

        self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        self.model = "deepseek-v4-flash"
        self.encoding = tiktoken.get_encoding("cl100k_base")

        # Task state machine
        self.use_state_machine = use_state_machine
        self.task_state = "idle"  # idle, planning, execution, validation, done
        self.task_description = None
        self.task_plan = None
        self.task_structure = None
        self.paused = False
        self.paused_state = None
        # None = not yet validated this cycle, True/False = last validation verdict
        self.invariants_satisfied: Optional[bool] = None

        # Set system prompt
        if use_state_machine:
            self.system_prompt = TASK_STATE_MACHINE_PROMPT.format(
                task_description=self.task_description or "",
                state=self.task_state,
                task_plan=self.task_plan or "",
                task_structure=self.task_structure or ""
            )
        else:
            self.system_prompt = system_prompt or "You are a helpful assistant. Respond concisely and directly."

        # Create memory directory
        self.memory_dir = memory_dir
        os.makedirs(memory_dir, exist_ok=True)

        # Initialize multi-layer memory
        self.memory = MemoryEngine(window_size=window_size)
        self._load_memory()

    def _load_memory(self) -> None:
        """Load persistent memory from disk."""
        try:
            prefix = f"{self.memory_dir}/"
            self.memory.load(prefix)
            print(f"✓ Loaded memory state from {self.memory_dir}/")
        except Exception as e:
            print(f"Warning: Could not load memory: {e}")

    def _save_memory(self) -> None:
        """Persist memory to disk."""
        try:
            prefix = f"{self.memory_dir}/"
            self.memory.save(prefix)
        except Exception as e:
            print(f"Error saving memory: {e}")

    def _update_state_machine_prompt(self) -> None:
        """Update system prompt with current state machine context."""
        if self.use_state_machine:
            self.system_prompt = TASK_STATE_MACHINE_PROMPT.format(
                task_description=self.task_description or "",
                state=self.task_state,
                task_plan=self.task_plan or "",
                task_structure=self.task_structure or ""
            )

    def start_task(self, description: str) -> Tuple[str, Dict[str, Any]]:
        """Begin task in planning state."""
        self.task_description = description
        self.task_state = "planning"
        self.task_plan = None
        self.task_structure = None
        self.invariants_satisfied = None
        self._update_state_machine_prompt()
        self._save_memory()
        return self.send_message(f"[TASK START]\n{description}")

    def set_task_state(self, state: str) -> bool:
        """Validate & transition state. DONE is hard-blocked while invariants are unresolved/violated,
        even on an explicit user override (e.g. 'mark valid') — code-enforced, not just prompt-enforced."""
        valid_states = ["planning", "execution", "validation", "done", "idle"]
        if state not in valid_states:
            return False

        if state == "done" and self.invariants_satisfied is not True:
            print(
                "⛔ Blocked: cannot enter DONE while invariants are unresolved or violated. "
                "Returning to EXECUTION to fix the discrepancy first."
            )
            self.task_state = "execution"
            self._update_state_machine_prompt()
            self._save_memory()
            return False

        self.task_state = state
        self._update_state_machine_prompt()
        self._save_memory()
        return True

    def set_task_plan(self, plan: str) -> None:
        """Store task plan."""
        self.task_plan = plan
        self._update_state_machine_prompt()
        self._save_memory()

    def set_task_structure(self, structure: str) -> None:
        """Store task structure/implementation."""
        self.task_structure = structure
        self._update_state_machine_prompt()
        self._save_memory()

    def pause_task(self) -> None:
        """Pause task at current state."""
        self.paused = True
        self.paused_state = self.task_state
        self._save_memory()

    def resume_task(self) -> Tuple[str, Dict[str, Any]]:
        """Resume from paused state without re-explaining."""
        if not self.paused:
            return "Task not paused", {}
        self.paused = False
        self._update_state_machine_prompt()
        self._save_memory()
        return self.send_message("[RESUME]")

    def task_status(self) -> Dict[str, Any]:
        """Get current task state machine status."""
        return {
            "task_description": self.task_description,
            "current_state": self.task_state,
            "paused": self.paused,
            "paused_state": self.paused_state,
            "task_plan": self.task_plan,
            "task_structure": self.task_structure,
            "invariants_satisfied": self.invariants_satisfied,
            "invariants": self.memory.invariants.list_all(),
        }

    def set_invariants(self, items: list) -> None:
        """Replace the invariant set (stored separately from dialogue)."""
        self.memory.invariants.set_all(items)
        self.invariants_satisfied = None
        self._save_memory()

    def add_invariant(self, text: str) -> None:
        """Add a single invariant."""
        self.memory.invariants.add(text)
        self.invariants_satisfied = None
        self._save_memory()

    def get_invariants(self) -> list:
        """List current invariants."""
        return self.memory.invariants.list_all()

    def _sync_state_from_response(self, assistant_response: str) -> None:
        """Parse [STATE: x] / [INVARIANTS: OK|VIOLATED] markers from the model's own reply and
        sync code-side state. DONE is hard-blocked here too, so the model can't self-report its
        way past unresolved invariants regardless of what the user asked it to say."""
        if not self.use_state_machine:
            return

        set_match = re.search(
            r"\[INVARIANTS_SET\](.*?)\[/INVARIANTS_SET\]", assistant_response, re.IGNORECASE | re.DOTALL
        )
        if set_match:
            raw_items = set_match.group(1).strip().splitlines()
            items = [re.sub(r"^[\-\*\d\.\)\s]+", "", line).strip() for line in raw_items]
            items = [item for item in items if item]
            self.set_invariants(items)

        inv_match = re.search(r"\[INVARIANTS:\s*(OK|VIOLATED)\]", assistant_response, re.IGNORECASE)
        if inv_match:
            self.invariants_satisfied = inv_match.group(1).upper() == "OK"

        state_match = re.search(r"\[STATE:\s*(\w+)\]", assistant_response, re.IGNORECASE)
        if not state_match:
            return
        parsed_state = state_match.group(1).lower()
        valid_states = {"planning", "execution", "validation", "done", "idle"}
        if parsed_state not in valid_states:
            return

        if parsed_state == "done" and self.invariants_satisfied is not True:
            print(
                "⛔ Model attempted DONE while invariants unresolved/violated — overridden to EXECUTION."
            )
            self.task_state = "execution"
        else:
            self.task_state = parsed_state

    def _count_tokens(self, messages: list) -> int:
        """Count tokens in message list."""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            tokens = len(self.encoding.encode(content))
            total += tokens
        return total

    def send_message(self, user_text: str) -> Tuple[str, Dict[str, Any]]:
        """Send message and get response with token metrics."""
        # Update prompt context before each message
        self._update_state_machine_prompt()

        user_tokens = len(self.encoding.encode(user_text))
        self.memory.add_message("user", user_text)

        messages_for_api = self.memory.get_messages_for_api(self.system_prompt)
        context_tokens = self._count_tokens(messages_for_api)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages_for_api
            )

            assistant_response = response.choices[0].message.content
            self.memory.add_message("assistant", assistant_response)
            self._sync_state_from_response(assistant_response)
            self._save_memory()

            metrics = {
                "user_input_tokens": user_tokens,
                "context_tokens": context_tokens,
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
                "memory_debug": self.memory.get_debug_info(),
            }

            return assistant_response, metrics

        except Exception as e:
            print(f"API Error: {e}")
            raise

    def checkpoint(self, name: str) -> None:
        """Create checkpoint in short-term memory."""
        self.memory.short_term.create_checkpoint(name)
        self._save_memory()

    def switch_branch(self, name: str) -> None:
        """Switch to dialogue branch."""
        self.memory.short_term.switch_branch(name)
        self._save_memory()

    def set_task(self, task_text: str) -> None:
        """Set working memory task."""
        self.memory.working.set_task(task_text)
        self._save_memory()

    def remember(self, text: str) -> None:
        """Add fact to long-term memory."""
        self.memory.long_term.remember_raw(text)
        self._save_memory()

    def switch_profile(self, profile_name: str) -> None:
        """Switch long-term profile."""
        self.memory.long_term.switch_profile(profile_name)
        self._save_memory()

    def set_mode(self, mode_name: str) -> bool:
        """Set assembly mode."""
        result = self.memory.set_mode(mode_name)
        if result:
            self._save_memory()
        return result

    def set_meta_setting(self, key: str, value: str) -> None:
        """Set profile behavioral meta-setting (tone, format_preference, verbosity)."""
        self.memory.long_term.set_meta_setting(key, value)
        self._save_memory()

    def get_meta_settings(self) -> Dict[str, str]:
        """Get current profile's meta-settings."""
        return self.memory.long_term.get_meta_settings()

    def status(self) -> Dict[str, Any]:
        """Get full agent status."""
        return {
            "short_term_branches": self.memory.short_term.list_branches(),
            "current_branch": self.memory.short_term.current_branch,
            "long_term_profiles": self.memory.long_term.list_profiles(),
            "current_profile": self.memory.long_term.current_profile,
            "profile_meta_settings": self.memory.long_term.get_meta_settings(),
            "assembly_mode": self.memory.assembly_mode,
            "debug_info": self.memory.get_debug_info(),
        }
