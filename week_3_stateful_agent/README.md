# Multi-Layer Memory AI Agent (Week 3, Day 11)

A Python-based AI agent with a **three-layer memory model** supporting dynamic context assembly, dialogue tree branching, and namespace profiling.

## Quick Start

### Prerequisites
```bash
pip install openai tiktoken
export DEEPSEEK_API_KEY="your-key-here"
```

### Run Interactive CLI
```bash
source ../deepseek-env/bin/activate
python main.py
```

### Run Validation Demo
```bash
source ../deepseek-env/bin/activate
python demo_validation.py
```

### Run Profiles Demo
```bash
source ../deepseek-env/bin/activate
python demo_profiles.py
```

---

## Architecture Overview

### Three Memory Layers

| Layer | Purpose | Strategy | Storage |
|-------|---------|----------|---------|
| **Short-term** | Conversation flow (last N messages) | Dialogue tree with branching | `short_term.json` |
| **Working** | Current task context | Linear, session-scoped | `working.json` |
| **Long-term** | User traits & facts | Namespace profiling (switchable) | `long_term.json` |

### Dynamic Assembly Modes

Control which layers are sent to the LLM API:

```
short_only       → System + Short-term only
short_working    → System + Short-term + Working task
short_long       → System + Short-term + Long-term profile
full_memory      → System + Short-term + Working + Long-term
```

---

## Usage Examples

### 1. Dialogue Tree Branching

Create an alternative conversation path without losing the original:

```bash
You: Explain OAuth2 implementation
Agent: OAuth2 flows involve three parties: resource owner, client, and server...

/checkpoint auth_v1
# Shared history now includes OAuth2 discussion

/branch alternative_approach
# New branch, starts empty (inherits shared history)

You: Actually, show me a simpler approach
Agent: For simple cases, consider just using JWT tokens...

/switch-branch auth_v1
# Back to original path, OAuth2 context still there

/branch auth_v1
```

### 2. Long-term Profiling

Maintain separate user contexts for different projects:

```bash
/switch-profile work_project_python
/remember I prefer FastAPI for web services
/remember Team uses PostgreSQL for databases

/switch-profile personal_learning
/remember I'm learning Go
/remember I prefer TDD approach

# Switch back to work context with different facts
/switch-profile work_project_python
```

### 3. Task-Focused Context

Keep working memory isolated from dialogue history:

```bash
/task Refactor the payment module
/mode short_working

You: What should I focus on?
Agent: (sees task context: "Refactor payment module")
       Focus on simplifying error handling...
```

### 4. Full Context (All Layers)

```bash
/mode full_memory

You: Help me implement the authentication system
Agent: (sees task + profile facts + dialogue history)
       Based on your Python preference and FastAPI setup...
```

### 5. Dynamic System Prompt Infiltration (Meta-Settings)

Configure behavioral constraints via profile meta-settings that are dynamically injected into the system prompt:

```bash
/switch-profile senior_engineer
/meta tone "Strict and concise, no fluff"
/meta format_preference "Code-first with minimal explanatory text"
/meta verbosity "Low"

You: How should I handle authentication?
Agent: (System prompt now includes behavioral constraints)
       [Code example with minimal explanation]

# Switch to mentor profile for same question
/switch-profile academic_mentor
/meta tone "Patient and encouraging"
/meta format_preference "Step-by-step explanations with inline comments"
/meta verbosity "High"

You: How should I handle authentication?
Agent: (Different system prompt with different constraints)
       Let's break this down into steps. First, understand the three main...
       [Detailed walkthrough with explanations]
```

---

## CLI Commands

### Short-term Dialogue Tree
```
/checkpoint <name>      Create save point of current dialogue
/branch <name>          Spawn new chat path from checkpoint
/switch-branch <name>   Jump to alternate conversation timeline
/branches               List available dialogue branches
```

### Long-term Profiles & Meta-Settings
```
/remember <text>                Add permanent fact to active profile
/switch-profile <name>          Switch global user traits (create if new)
/profiles                       List available profiles
/meta <key> <value>             Set behavioral meta-setting:
                                  - tone (e.g., "Strict and concise")
                                  - format_preference (e.g., "Code-only")
                                  - verbosity (e.g., "Low", "Medium", "High")
/meta-show                      Display current profile's meta-settings
```

### Working Memory
```
/task <text>            Set or overwrite active target task
```

### Assembly Mode
```
/mode <mode_name>       Select payload assembly strategy:
                        - short_only
                        - short_working
                        - short_long
                        - full_memory
```

### Status & Info
```
/status                 Show current configuration
/help                   Show all commands
/exit or /quit          Exit program
```

---

## File Structure

```
week_3_stateful_agent/
├── main.py                  # Interactive CLI entry point
├── agent.py                 # DeepSeekAgent class
├── memory.py                # Three-layer memory + meta-settings
├── demo_validation.py       # Validation scenario demo (branching & modes)
├── demo_profiles.py         # Meta-settings infiltration demo (5 scenarios)
├── ARCHITECTURE.md          # Detailed storage & design docs
├── README.md               # This file
└── .memory/                # Persistent storage (auto-created)
    ├── short_term.json
    ├── working.json
    └── long_term.json
```

---

## Memory Storage Format

### Short-term Memory (short_term.json)
```json
{
  "layer": "short_term",
  "shared_history": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ],
  "current_branch": "main",
  "branches": {
    "main": [...],
    "branch_a": [...],
    "branch_b": [...]
  }
}
```

### Working Memory (working.json)
```json
{
  "layer": "working",
  "task": "Refactor payment module",
  "context": {
    "deadline": "2024-06-20",
    "status": "in_progress"
  },
  "errors": ["IndexError at line 42"]
}
```

### Long-term Memory (long_term.json)
```json
{
  "layer": "long_term",
  "current_profile": "senior_engineer",
  "profiles": {
    "default": {
      "_meta_settings": {
        "tone": "Neutral and helpful",
        "format_preference": "Clear and well-structured",
        "verbosity": "Medium"
      }
    },
    "senior_engineer": {
      "_meta_settings": {
        "tone": "Strict and concise, no fluff",
        "format_preference": "Code-first with minimal explanatory text",
        "verbosity": "Low"
      },
      "favorite_language": "Python 3.12",
      "team_size": "5"
    },
    "academic_mentor": {
      "_meta_settings": {
        "tone": "Patient and encouraging",
        "format_preference": "Step-by-step explanations with inline comments",
        "verbosity": "High"
      },
      "student_level": "Beginner",
      "learning_style": "Hands-on with theory"
    }
  }
}
```

**Note:** Each profile includes `_meta_settings` (system key with underscore prefix) containing behavioral constraints that are dynamically injected into the system prompt.

---

## Dynamic System Prompt Infiltration (Meta-Settings Feature)

Each profile can define behavioral meta-settings that are **dynamically injected into the system prompt** before sending to the LLM API. This allows configuring agent behavior without code changes.

### Meta-Settings

Three configurable settings per profile:

| Setting | Examples | Effect |
|---------|----------|--------|
| `tone` | "Strict", "Patient", "Pragmatic" | Controls voice & communication style |
| `format_preference` | "Code-first", "Detailed explanations" | Controls response structure |
| `verbosity` | "Low", "Medium", "High" | Controls response length & detail |

### How It Works

1. Base system prompt: `"You are a helpful AI Assistant"`
2. Fetch active profile's meta-settings
3. Dynamically append behavioral constraints:
   ```
   [CRITICAL BEHAVIORAL CONSTRAINTS FROM PROFILE]
   - Tone: {value}
   - Format Preference: {value}
   - Verbosity Level: {value}
   ```
4. Send injected prompt + context + messages to API

### Use Cases

- **Code Review vs Security Audit:** Same question, different scrutiny lens
- **Student vs Professional:** Different verbosity & explanation depth
- **MVP vs Production:** Different priorities (speed vs quality)
- **Senior Engineer vs Mentor:** Different tone & code-to-text ratio

### Demo

Run the profiles demo to see 5 scenarios:
```bash
python demo_profiles.py
```

---

## Design Principles

### 1. Isolation by Default
- Branches have physically separate message histories
- Only the active branch's messages are sent to the API
- Switching modes excludes entire layers from payload

### 2. Persistent & Resumable
- All state saved to `.memory/` directory
- Auto-load on startup
- Switch between branches/profiles without losing context

### 3. Token Efficiency
- Window-based short-term trimming
- Mode-based context filtering
- Switching branches excludes alternate-path messages

### 4. Namespace-based Profiling (Not Git Branching)
- Long-term uses **profiles** (isolated contexts), not branches
- Switching profile = complete replacement of traits
- No merge complexity, single source of truth per profile

### 5. Dynamic System Prompt Infiltration
- Meta-settings automatically injected into system prompt
- No prompt engineering required — just set profile constraints
- Changes apply immediately without code modification
- Each profile has independent behavioral configuration

---

## Validation & Demos

### Multi-Layer Memory Validation
Run the validation scenario to see three-layer memory in action:
```bash
python demo_validation.py
```

Validates:
1. Creating profiles with persistent facts
2. Setting tasks in working memory
3. Chatting in full-memory mode (all layers visible)
4. Creating checkpoints and branching
5. Mode switching to disable/enable layers
6. Branch isolation preventing message contamination

### Dynamic System Prompt Infiltration Demo
Run the profiles demo to see meta-settings in action:
```bash
python demo_profiles.py
```

Demonstrates:
1. **Scenario 1:** Senior Engineer Profile (strict, code-focused)
2. **Scenario 2:** Academic Mentor Profile (patient, detailed)
3. **Scenario 3:** Tech Lead Profile (balanced, architecture-focused)
4. **Scenario 4:** Profile Switching (same question, different responses)
5. **Scenario 5:** Full context assembly with meta-settings
6. Storage format showing `_meta_settings` structure

---

## Integration with Task_10

This implementation builds on the **task_10 strategies**:

| Task_10 | Week_3 Extension |
|---------|------------------|
| `SlidingWindowStrategy` | → Short-term layer (windowed messages) |
| `StickyFactsStrategy` | → Long-term layer (persistent facts) |
| `BranchingStrategy` | → Dialogue tree (shared history + branches) |
| - | + Assembly modes (dynamic layer inclusion) |
| - | + Namespace profiling (not just facts) |
| - | + Working memory (linear task context) |
| - | + **Meta-settings infiltration** (dynamic system prompt) |

---

## Future Enhancements

1. **SQLite Backend:** Scale beyond JSON for large histories
2. **Compression:** Archive old branches, load on demand
3. **Fact Extraction:** Background API call to auto-extract facts from dialogue
4. **Branching Diff:** Show delta between branches
5. **Profile Inheritance:** Profiles inherit from parent with overrides
6. **Meta-Settings Presets:** Built-in profiles (code_reviewer, educator, architect, etc.)
7. **Meta-Settings Templates:** Share meta-settings across teams
8. **Auto-Calibration:** Measure response quality and auto-adjust verbosity
9. **REST API:** Expose agent as web service
10. **Multi-Agent:** Support multiple agents with shared profile store

---

## API Reference

### DeepSeekAgent

```python
agent = DeepSeekAgent(
    api_key="...",
    system_prompt="You are helpful",
    window_size=6,
    memory_dir=".memory"
)

# Send message
response, metrics = agent.send_message("Hello!")

# Short-term control
agent.checkpoint("save_point")
agent.switch_branch("alt_path")

# Long-term control
agent.switch_profile("work_context")
agent.remember("I prefer Python")
agent.set_meta_setting("tone", "Strict and concise")
agent.set_meta_setting("verbosity", "Low")

# Meta-settings
meta = agent.get_meta_settings()  # Get current profile's meta-settings

# Working control
agent.set_task("Write a function")

# Assembly control
agent.set_mode("full_memory")

# Status
status = agent.status()
```

### MemoryEngine

```python
engine = MemoryEngine(window_size=6)

# Get final API payload
messages = engine.get_messages_for_api(system_prompt)

# Save/load
engine.save(".memory/")
engine.load(".memory/")

# Debug info
info = engine.get_debug_info()
```

---

## Troubleshooting

### API Key Not Found
```bash
export DEEPSEEK_API_KEY="sk-xxx"
```

### Memory Files Not Loading
- Check `.memory/` directory exists
- Verify JSON files are valid (use `python -m json.tool file.json`)
- Clear `.memory/` to start fresh

### Memory Contamination
- Verify current mode: `/mode`
- Check active branch: `/status`
- Mode `short_only` excludes all external context

---

## Contributing

See ARCHITECTURE.md for detailed storage design and future extension points.

---

## License

Educational project (Week 3 Challenge)
