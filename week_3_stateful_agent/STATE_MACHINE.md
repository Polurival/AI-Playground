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
