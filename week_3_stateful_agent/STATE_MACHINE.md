# Task State Machine

Formal task execution state machine: **planning → execution → validation ⟷ execution → done**

## States

### 1. PLANNING
**Role:** Architect solution  
**Output:**
- Processes/Features
- Design & UI/UX
- Tech Stack
- Architecture (components, modules)
- Database schema (if needed)

**Transition:** User confirms "ready to execute" → EXECUTION

---

### 2. EXECUTION
**Role:** Propose implementation structure  
**Output:**
- Directory tree
- File list with descriptions
- Key files with pseudo-code
- Dependencies & imports

**Modes:**
- Initial: First implementation proposal
- Correction: Fix validation issues (shows `[EXECUTION: corrections]`)

**Transition:** User confirms "validate this" → VALIDATION

---

### 3. VALIDATION
**Role:** Cross-check implementation vs plan  
**Checks:**
1. Plan ↔ Implementation mapping
2. All features covered?
3. Architecture followed?
4. Conflicts/gaps?

**Output:** Validation checklist + issues

**Outcomes:**
- ✅ **No issues** → Proceed to DONE
- ❌ **Issues found** → Auto-loop back to EXECUTION (corrections mode)

---

### 4. DONE
**Role:** Summarize & suggest improvements  
**Output:**
1. Completed checklist
2. What was accomplished
3. Potential improvements/extensions
4. Next steps

---

## Commands

| Command | Effect |
|---------|--------|
| `pause` | Pause at current state, save context |
| `resume` | Continue from pause without re-explaining |
| `status` | Show current task state & context |
| `back` | Jump to previous state |
| `mark valid` | Override validation, force DONE |
| Regular message | Chat with agent (may trigger auto-transition) |

---

## Usage

```python
from agent import DeepSeekAgent

# Create agent with state machine
agent = DeepSeekAgent(use_state_machine=True)

# Start task
response, metrics = agent.start_task("Build a Spanish learning app")
# Agent enters PLANNING state, proposes architecture

# Send message (e.g., user confirmation)
response, metrics = agent.send_message("ready to execute")
# Agent transitions to EXECUTION, proposes structure

# Check status
status = agent.task_status()
print(status)

# Pause
agent.pause_task()

# Resume
response, metrics = agent.resume_task()

# Jump states
agent.set_task_state("done")
```

---

## Validation Loop

```
PLANNING
   ↓ (user ready)
EXECUTION
   ↓ (user validate)
VALIDATION
   ├→ ✅ Issues? No  → DONE
   └→ ❌ Issues? Yes → EXECUTION [corrections mode]
        ↓ (fixes applied)
      VALIDATION
```

---

## Auto-Transition Rules

- **Planning → Execution:** After user explicitly confirms plan is complete
- **Execution → Validation:** After user explicitly confirms structure ready
- **Validation → Done:** When validation finds no issues
- **Validation → Execution:** When validation finds issues (automatic loop)

---

## State Machine Prompt Context

Agent always knows:
- Current task description
- Current state
- Saved task plan
- Saved task structure

Update via:
- `set_task_plan(plan_text)`
- `set_task_structure(structure_text)`

Automatic on state transitions.

---

## Code-Enforced Transition Table

`ALLOWED_TRANSITIONS` in `agent.py` is the single source of truth for legal moves — checked in
both `set_task_state()` (programmatic/CLI) and `_sync_state_from_response()` (model's own
`[STATE: x]` marker). Anything not listed is refused, no matter who asks for it (user command,
"mark valid", or the model itself):

```
idle       -> planning
planning   -> execution, idle
execution  -> validation, planning
validation -> done, execution
done       -> validation
```

This is what makes "no implementation before an approved plan" and "no done without validation"
actual code guarantees rather than just prompt instructions:
- `execution` is unreachable from `idle` — must pass through `planning` first.
- `done` is unreachable from anywhere except `validation` — and even from `validation`, the
  invariants gate (above) still applies on top of the transition check.
- If the model emits a marker for an illegal jump (e.g. `[STATE: done]` while in `planning`),
  `_sync_state_from_response()` ignores it and logs `⛔ Model declared illegal jump ...` —
  state stays where it was.

Run `python demo_transition_guard.py` for an offline (no API key/network) proof of all of the
above, including the pause → resume continuity check.

---

## Invariants (hard constraints)

Invariants are non-negotiable rules — chosen architecture, accepted tech decisions, stack limits,
business rules — that the agent must never violate, even on explicit user request.

**Storage:** separate from dialogue. `InvariantsMemory` (`memory.py`) persists to its own
`invariants.json` file, distinct from `short_term.json` / `working.json` / `long_term.json`.
It's injected into every API call as its own system message (`MemoryEngine.get_system_messages`),
regardless of assembly mode, so it's never trimmed by the dialogue window.

**Setting them programmatically:**
```python
agent.set_invariants(["Backend must be FastAPI", "No third-party paid APIs", "SQLite only"])
agent.add_invariant("All endpoints must be stateless")
agent.get_invariants()
```

**Setting them through chat (the normal path):** in `PLANNING`, if no invariants exist yet, the agent
asks the user for them. Whatever the user types in chat is NOT persisted automatically — chat is just
the dialogue layer. To actually persist, the model is required to end that turn with a machine-readable
block:
```
[INVARIANTS_SET]
Must be an Android app
Must use MVVM architecture
[/INVARIANTS_SET]
```
`_sync_state_from_response()` regexes this block out of the model's reply and calls `set_invariants()`
with the full parsed list (always the complete current set, not a diff). The same block is required any
time the user explicitly amends an invariant later — the model must flag the conflict, get explicit
confirmation, then re-emit the updated full list. Without this marker, invariants stay empty even if
the conversation "talks about" them — this was a real bug found in testing (model discussed invariants
in chat but `invariants.json` stayed `{"invariants": []}` and the architecture was later swapped from
MVVM to MVI with zero pushback, since there was nothing in the hard-constraint store to violate).

**Enforcement at VALIDATION (code-level, not just prompt-level):**
- The agent's validation response must end with `[INVARIANTS: OK]` or `[INVARIANTS: VIOLATED]`.
- `_sync_state_from_response()` parses that marker and sets `agent.invariants_satisfied`.
- `set_task_state("done")` and the auto-transition path in `send_message` both refuse to enter
  `done` while `invariants_satisfied is not True` — forcing the state back to `execution` instead.
- This holds even if the user types `mark valid` or explicitly asks to skip ahead: the check is a
  Python `if`, not something the model can be talked out of.

**Conflict handling:** when a request would violate an invariant, the agent must name the exact
invariant, explain why the request conflicts with it, and propose a compliant alternative instead
of silently complying or silently refusing.

---

## Run Demo

```bash
source ../deepseek-env/bin/activate
python demo_state_machine.py # - this will launch quick flow for video demo. If launch agent.py, agent will ask clarifying questions in planning mode, etc.
```

Task: "Create a Spanish language learning application"

Expected flow:
1. Agent proposes learning features, tech stack, architecture
2. You confirm "ready to execute"
3. Agent proposes project structure
4. You say "validate this"
5. Agent checks against plan
6. If issues → auto-loop to step 3 (corrections)
7. If valid → agent provides summary & improvements
