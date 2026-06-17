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

---

## CLI Commands

### Short-term Dialogue Tree
```
/checkpoint <name>      Create save point of current dialogue
/branch <name>          Spawn new chat path from checkpoint
/switch-branch <name>   Jump to alternate conversation timeline
/branches               List available dialogue branches
```

### Long-term Profiles
```
/remember <text>        Add permanent fact to active profile
/switch-profile <name>  Switch global user traits (create if new)
/profiles               List available profiles
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
├── memory.py                # Three-layer memory implementation
├── demo_validation.py       # Validation scenario demo
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
  "current_profile": "work_project",
  "profiles": {
    "work_project": {
      "favorite_language": "Python 3.12",
      "team_size": "5",
      "deadline": "Q3 2024"
    },
    "personal": {
      "learning_goal": "Go",
      "approach": "TDD"
    }
  }
}
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

---

## Experimental Validation

Run the validation scenario to see all three layers in action:

```bash
python demo_validation.py
```

This demonstrates:
1. Creating a profile with persistent facts
2. Setting a task in working memory
3. Chatting in full-memory mode (agent sees all context)
4. Creating a checkpoint and branching
5. Switching to short_working mode (long-term disabled)
6. Verifying the agent can't see facts when mode disables long-term
7. Switching back to original branch (facts intact)
8. Proving branch isolation prevents message contamination

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

---

## Future Enhancements

1. **SQLite Backend:** Scale beyond JSON for large histories
2. **Compression:** Archive old branches, load on demand
3. **Fact Extraction:** Background API call to auto-extract facts from dialogue
4. **Branching Diff:** Show delta between branches
5. **Profile Inheritance:** Profiles inherit from parent with overrides
6. **REST API:** Expose agent as web service
7. **Multi-Agent:** Support multiple agents with shared profile store

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
