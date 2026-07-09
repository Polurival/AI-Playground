import os
import re
from openai import OpenAI
import tiktoken
from typing import Tuple, Dict, Any, Optional
from memory import MemoryEngine

# ---------------------------------------------------------------------------
# Model backends
#
# Both the remote DeepSeek API and a LOCAL Ollama server speak the same
# OpenAI-compatible chat API, so a single OpenAI() client works for either —
# only base_url / model / api-key handling differ. The registry below is the
# single source of truth; `/model <name>` in the CLI flips between them at
# runtime without dropping the conversation or memory.
#
# "local" points at Ollama (see ../week_6_local_LLM/README.md): no cloud, no
# API key, no network — everything runs on this machine.
# ---------------------------------------------------------------------------
MODEL_BACKENDS: Dict[str, Dict[str, Any]] = {
    "deepseek": {
        "label": "DeepSeek (remote cloud API)",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
        "api_key_env": "DEEPSEEK_API_KEY",  # required
        "local": False,
    },
    "local": {
        "label": "Qwen2.5:3b via Ollama (local, offline)",
        "base_url": "http://localhost:11434/v1",
        "model": "qwen2.5:3b",
        "api_key_env": None,  # Ollama ignores the key
        "local": True,
    },
}

DEFAULT_BACKEND = os.environ.get("AGENT_BACKEND", "deepseek")

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


# Explicit transition table — the single source of truth for which state can move to which.
# Forward path:  idle -> planning -> execution -> validation -> done
# Allowed back:  planning -> idle, execution -> planning, validation -> execution, done -> validation
# Loop:          validation -> execution (correction loop)
# Reopen:        done -> planning (user-initiated revision of an already-finished task)
# Anything not listed here is an illegal jump and is refused in code, regardless of what the
# model says (e.g. [STATE: done]) or what the user types (e.g. "mark valid").
ALLOWED_TRANSITIONS: Dict[str, set] = {
    "idle": {"planning"},
    "planning": {"execution", "idle"},
    "execution": {"validation", "planning"},
    "validation": {"execution", "done"},
    "done": {"validation", "planning"},
}


class DeepSeekAgent:
    """Multi-layer memory agent with dynamic context assembly."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        system_prompt: Optional[str] = None,
        window_size: int = 6,
        memory_dir: str = ".memory",
        use_state_machine: bool = True,
        backend: str = DEFAULT_BACKEND,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        # Build self.client / self.model / self.backend from the registry.
        # Raises ValueError only if a *remote* backend is missing its API key —
        # the local (Ollama) backend needs none, so it works with no cloud creds.
        self._configure_backend(backend, api_key=api_key, model=model, base_url=base_url)
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

    def _configure_backend(
        self,
        backend: str,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        """(Re)build the OpenAI client for the given backend. Called at init and
        by switch_backend() — it only swaps client/model/base_url, never touches
        memory, so the conversation survives a mid-session model switch."""
        if backend not in MODEL_BACKENDS:
            raise ValueError(
                f"Unknown backend '{backend}'. Available: {', '.join(MODEL_BACKENDS)}"
            )
        cfg = MODEL_BACKENDS[backend]
        resolved_base_url = base_url or cfg["base_url"]
        resolved_model = model or cfg["model"]

        key_env = cfg["api_key_env"]
        if key_env:
            resolved_key = api_key or os.environ.get(key_env)
            if not resolved_key:
                raise ValueError(
                    f"{key_env} environment variable not set (required for backend '{backend}')"
                )
        else:
            # Local backends (Ollama) ignore the key, but the OpenAI SDK still
            # requires a non-empty string.
            resolved_key = api_key or "local"

        self.backend = backend
        self.model = resolved_model
        self.base_url = resolved_base_url
        self.client = OpenAI(api_key=resolved_key, base_url=resolved_base_url)

    def switch_backend(self, backend: str) -> bool:
        """Flip the active model backend at runtime (used by the /model command).
        Returns True on success; on failure (unknown backend or missing API key)
        it prints why and keeps the current backend untouched."""
        previous = getattr(self, "backend", None)
        if backend == previous:
            print(f"Already using backend '{backend}'.")
            return True
        try:
            self._configure_backend(backend)
        except ValueError as e:
            print(f"✗ Could not switch to '{backend}': {e}")
            return False
        print(f"✓ Model backend: {previous} → {backend} ({self.model} @ {self.base_url})")
        return True

    def backend_info(self) -> Dict[str, Any]:
        """Describe the currently active backend (for /status and /model)."""
        cfg = MODEL_BACKENDS.get(self.backend, {})
        return {
            "backend": self.backend,
            "label": cfg.get("label", self.backend),
            "model": self.model,
            "base_url": self.base_url,
            "local": cfg.get("local", False),
        }

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

    def set_task_state(self, state: str, force: bool = False) -> bool:
        """Validate & transition state against ALLOWED_TRANSITIONS. DONE is additionally
        hard-blocked while invariants are unresolved/violated, even on an explicit user
        override (e.g. 'mark valid') — code-enforced, not just prompt-enforced.

        force=True bypasses the transition table (used for legitimate resets like idle/start_task)
        but never bypasses the invariants gate on done."""
        valid_states = ["planning", "execution", "validation", "done", "idle"]
        if state not in valid_states:
            return False

        if not force and state not in ALLOWED_TRANSITIONS.get(self.task_state, set()):
            print(
                f"⛔ Blocked: illegal transition {self.task_state} → {state}. "
                f"Allowed from '{self.task_state}': {sorted(ALLOWED_TRANSITIONS.get(self.task_state, set()))}"
            )
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

        if parsed_state == self.task_state:
            return  # no-op, model just restated current state

        if parsed_state not in ALLOWED_TRANSITIONS.get(self.task_state, set()):
            print(
                f"⛔ Model declared illegal jump {self.task_state} → {parsed_state} "
                f"— ignored, state stays at '{self.task_state}'."
            )
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

            # Ollama's OpenAI-compatible endpoint usually returns usage, but guard
            # against a backend that omits it so local mode never crashes here.
            usage = getattr(response, "usage", None)
            metrics = {
                "user_input_tokens": user_tokens,
                "context_tokens": context_tokens,
                "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
                "total_tokens": getattr(usage, "total_tokens", 0) or 0,
                "memory_debug": self.memory.get_debug_info(),
            }

            return assistant_response, metrics

        except Exception as e:
            print(f"API Error ({self.backend} @ {self.base_url}): {e}")
            if MODEL_BACKENDS.get(self.backend, {}).get("local"):
                print(
                    f"Is Ollama running? Start it with `sudo snap start ollama` "
                    f"(or `ollama serve`) and pull the model with `ollama pull {self.model}`."
                )
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
