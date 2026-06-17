# Multi-Layer Memory AI Agent - Architecture & Storage Design

## Overview

The `DeepSeekAgent` implements a **three-layer memory model** with **branching & profiling strategies** optimized for each memory type's unique characteristics.

```
┌─────────────────────────────────────────────────────────┐
│                   DeepSeekAgent                         │
├─────────────────────────────────────────────────────────┤
│  MemoryEngine                                           │
│  ├─ SHORT-TERM (Dialogue Tree Branching)               │
│  ├─ WORKING (Linear Task Context)                       │
│  ├─ LONG-TERM (Namespace Profiling)                     │
│  └─ ASSEMBLY_MODE (Dynamic Context Assembly)           │
└─────────────────────────────────────────────────────────┘
```

---

## 1. Memory Layers

### 1.1 Short-Term Memory (Dialogue Tree)

**Purpose:** Maintain conversation flow with checkpoint/branching support

**Storage Model:**
```
short_term.json
{
  "layer": "short_term",
  "shared_history": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ],
  "current_branch": "branch_a",
  "branches": {
    "main": [...],
    "branch_a": [...],
    "branch_b": [...]
  }
}
```

**Key Concept: Shared History + Branch-Specific Messages**

- **Shared History:** All messages accumulated before the first checkpoint belong here. Common context across branches.
- **Branches:** Each branch is an independent message array starting from a checkpoint.
- **API Payload:** `shared_history + current_branch_messages` (trimmed to window size)

**Operations:**
- `add_message(role, content)` → appends to current branch only
- `create_checkpoint(name)` → merges current branch to shared history, creates new empty branch
- `switch_branch(name)` → switches active branch, inherits shared history
- `get_messages()` → returns combined (shared + branch, trimmed)

**Token Optimization:**
When branching from `Branch_A` to `Branch_B` and setting a different mode, messages from `Branch_A` are physically excluded from the API payload, preventing "hallucination contamination" and saving tokens.

---

### 1.2 Working Memory (Task Context)

**Purpose:** Hold session-specific, linear task data

**Storage Model:**
```
working.json
{
  "layer": "working",
  "task": "Write an authentication module",
  "context": {
    "framework": "FastAPI",
    "deadline": "2024-06-20"
  },
  "errors": [
    "Module not found: jwt",
    "Import error at line 42"
  ]
}
```

**Key Concept: Flat, Session-Scoped**

- No branching or versioning — purely linear
- Scoped to current working session
- Can be cleared at session end via `clear()`
- Formatted as system message when mode includes `working`

**Operations:**
- `set_task(text)` → overwrites task
- `add_context(key, value)` → adds/updates context entry
- `add_error(text)` → appends error log
- `get_context_text()` → returns formatted text for API
- `clear()` → resets all

---

### 1.3 Long-Term Memory (Namespace Profiles)

**Purpose:** Persistent user traits, preferences, and constraints

**Storage Model:**
```
long_term.json
{
  "layer": "long_term",
  "current_profile": "personal_profile",
  "profiles": {
    "default": {},
    "personal_profile": {
      "favorite_language": "Kotlin",
      "preferred_framework": "Ktor",
      "experience_level": "Senior"
    },
    "work_project_alpha": {
      "favorite_language": "Python 3.12",
      "tech_stack": "FastAPI, SQLAlchemy"
    }
  }
}
```

**Key Concept: Switchable Namespaces (NOT Git-like branches)**

- Multiple isolated profiles, each a flat key-value store
- **Switching profiles** replaces global context entirely
- Single active profile at any time
- Switching from `personal_profile` to `work_project_alpha` swaps all global traits

**Operations:**
- `switch_profile(name)` → activates profile (creates if not exists)
- `remember(key, value)` → adds fact to active profile
- `remember_raw(text)` → logs raw text with auto-generated key
- `get_profile_text()` → returns formatted profile for API
- `list_profiles()` → returns profile names

---

## 2. Dynamic Context Assembly (Payload Builder)

The **Assembly Mode** determines which layers are included in the API payload:

### Modes:

| Mode | Layers Sent | Use Case |
|------|------------|----------|
| `short_only` | System Prompt + Short-term Branch | Isolated dialogue, no context bleeding |
| `short_working` | Short-term + Working Task Context | Focus on task at hand |
| `short_long` | Short-term + Long-term Profile | Use global traits without task context |
| `full_memory` | Short-term + Working + Long-term | Maximum context (all three layers) |

### Example Payload Assembly (full_memory mode):

```python
messages = [
  {"role": "system", "content": "You are a helpful assistant..."},
  {"role": "system", "content": "Current Task: Write an auth module\nContext: {...}"},  # Working
  {"role": "system", "content": "User Profile (work_project_alpha):\n  - favorite_language: Python 3.12\n  - ..."},  # Long-term
  {"role": "user", "content": "Rewrite module in my favorite language"},  # Short-term
  {"role": "assistant", "content": "..."},  # Short-term
]
```

---

## 3. Persistent Storage (Disk Layout)

Files are stored in `.memory/` directory:

```
.memory/
├── short_term.json    → Dialogue tree + branches
├── working.json       → Task & context
└── long_term.json     → Profiles & facts
```

**Load/Save Strategy:**
- Automatic save after every API call via `_save_memory()`
- Load on agent init via `_load_memory()`
- Each layer independently serializable

---

## 4. Experimental Validation Scenario

The following scenario demonstrates the three-layer system in action:

### Setup:
```bash
python main.py
```

### Step 1: Create Long-term Profile + Facts
```
/switch-profile MobileDev
✓ Switched to profile: 'MobileDev'

/remember My favorite language is Kotlin
✓ Fact recorded in profile 'MobileDev'
```

### Step 2: Set Working Task
```
/task Write an authentication module
✓ Task set
```

### Step 3: Chat in Branch A (Full Memory Mode)
```
/mode full_memory
✓ Mode set to 'full_memory'

You: Implement auth using my favorite framework
Agent: I'll help you build Ktor Authentication...
       (Agent knows "Kotlin" from long-term, sees task from working, uses dialogue from short-term)
```

### Step 4: Create Checkpoint & Switch Branch
```
/checkpoint branch_a_checkpoint
✓ Checkpoint 'branch_a_checkpoint' created

/branch branch_b
✓ Switched to branch 'branch_b'
```

### Step 5: Disable Long-term Memory
```
/mode short_working
✓ Mode set to 'short_working'

You: Rewrite the module in my favorite language
Agent: I can rewrite it, but I need to know your preferred language.
       (Long-term memory disabled → agent CANNOT see "Kotlin" fact)
```

### Step 6: Verify Branch A Still Has Full Context
```
/switch-branch branch_a
/mode full_memory

You: What was my favorite framework again?
Agent: Your favorite framework is Ktor.
       (Back in original branch with full mode → sees all facts)
```

**Key Observations:**
- `branch_b` with `short_working` mode: **cannot** access language preference (isolated)
- `branch_a` with `full_memory` mode: **still** accesses all facts (preserved)
- Messages from `branch_a` physically excluded from `branch_b` API payloads (no contamination)

---

## 5. Class Hierarchy

```
MemoryLayer (ABC)
├── ShortTermMemory
│   ├── shared_history: List[Message]
│   ├── branches: Dict[name → List[Message]]
│   └── current_branch: str
├── WorkingMemory
│   ├── task: str
│   ├── context: Dict[str, Any]
│   └── errors: List[str]
└── LongTermMemory
    ├── profiles: Dict[name → Dict[key, value]]
    └── current_profile: str

MemoryEngine
├── short_term: ShortTermMemory
├── working: WorkingMemory
├── long_term: LongTermMemory
├── assembly_mode: str
└── Methods:
    ├── get_messages_for_api() → List[Message]
    ├── set_mode()
    ├── save() → disk
    └── load() ← disk

DeepSeekAgent
├── memory: MemoryEngine
├── client: OpenAI client
└── Methods:
    ├── send_message()
    ├── checkpoint() → short_term.create_checkpoint()
    ├── switch_branch() → short_term.switch_branch()
    ├── set_task() → working.set_task()
    ├── remember() → long_term.remember_raw()
    ├── switch_profile() → long_term.switch_profile()
    └── set_mode() → memory.set_mode()
```

---

## 6. Token Optimization via Layered Branching

**Problem:** In monolithic memory systems, switching branches still contaminates context with messages from alternate paths.

**Solution:** Git-like dialogue tree + mode-based assembly

**Example:**
- User explores authentication in `branch_a` (10 messages)
- Creates checkpoint, switches to `branch_b`
- Asks "Rewrite in Python" in `short_working` mode
- API payload = system + working task (Python-specific) + `branch_b` messages (only 2 new ones)
- `branch_a`'s 10 messages **NOT** sent → saves ~500+ tokens per request

**Mode Filtering:**
```python
# branch_a is active with full_memory mode
get_messages_for_api() → [system, task, profile, ...10 branch_a messages]

# switch to branch_b with short_working mode
get_messages_for_api() → [system, task, ...2 branch_b messages]
# Long-term profile excluded via mode, branch_a messages never sent
```

---

## 7. CLI Commands

| Command | Effect |
|---------|--------|
| `/checkpoint <name>` | Shared history += current branch; create new empty branch |
| `/branch <name>` | Switch to branch (auto-create if new) |
| `/switch-branch <name>` | Alias for `/branch` |
| `/remember <text>` | Append fact to active long-term profile |
| `/switch-profile <name>` | Switch global profile context |
| `/task <text>` | Set active task in working memory |
| `/mode <mode>` | Change assembly mode |
| `/status` | Show all branch/profile/mode info |
| `/branches` | List dialogue branches |
| `/profiles` | List long-term profiles |
| `/help` | Show command list |

---

## 8. Future Extensions

1. **SQLite Fallback:** Replace JSON with SQLite for > 100k message histories
2. **Compression:** Archive older branches to disk, load on demand
3. **Fact Extraction:** Background API call to auto-extract facts from dialogue (like sticky_facts strategy in task_10)
4. **Branching Diff:** Show delta between branches before switching
5. **Profile Inheritance:** Profiles inherit from parent profile with override support
