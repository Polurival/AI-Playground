# Task 10: Multi-Strategy Context Management for DeepSeek Agent

## Overview

This task implements the **Strategy Pattern** for managing conversation context in a Python-based AI agent. The agent now supports three distinct context management strategies without requiring heavy summarization, with seamless switching via CLI.

## Architecture

### Core Components

1. **strategies.py** - Strategy interface and implementations
   - `ContextStrategy`: Abstract base class defining the interface
   - `SlidingWindowStrategy`: Keep last N messages
   - `StickyFactsStrategy`: Maintain key-value memory of facts
   - `BranchingStrategy`: Support conversation branches/checkpoints

2. **agent.py** - Refactored DeepSeekAgent
   - Strategy pattern encapsulation
   - Clean separation of concerns
   - Token tracking and analytics
   - Seamless strategy switching at runtime

3. **main.py** - Interactive CLI
   - Strategy selection menu at startup
   - Command-based interface (`/help`, `/strategy`, etc.)
   - Real-time metrics display

4. **COMPARISON.md** - Detailed analysis
   - Strategy comparison across 4 vectors
   - Real-world use case simulation
   - Token cost analysis

## Strategy Details

### 1. Sliding Window (`sliding_window`)

**Logic:** Keeps only the last N messages. When window is exceeded, oldest messages are permanently dropped.

**Payload Structure:**
```
[System Prompt] + [Last N Messages]
```

**When to use:**
- Quick exploratory chats
- Limited budget scenarios
- Single-turn or short interactions

**Example:**
```python
agent = DeepSeekAgent(strategy="sliding_window", window_size=6)
# After 7+ messages, message 1 is dropped to make room
```

**Debug Output:**
```
[DEBUG - Sliding Window] Evicted 2 old messages
```

---

### 2. Sticky Facts (`sticky_facts`)

**Logic:** Maintains a dedicated dictionary of key-value facts extracted via background API call. Recent messages (up to N) are kept alongside.

**Payload Structure:**
```
[System Prompt] + [System Message: "Core Facts: {...}"] + [Last N Messages]
```

**Background Process:** After every user message, the agent makes a lightweight API call to update facts (e.g., "primary_key": "UUID").

**When to use:**
- Requirement gathering
- Constraint-heavy tasks
- Multi-turn decision-making

**Example:**
```python
agent = DeepSeekAgent(strategy="sticky_facts", window_size=6)
# Facts like constraints, decisions, project goals are auto-extracted and preserved
```

**Debug Output:**
```
[DEBUG - Facts] Updated core facts: {'database': 'PostgreSQL', 'primary_key': 'UUID'}
```

---

### 3. Branching (`branching`)

**Logic:** Supports creating named "checkpoints" of the conversation. From a checkpoint, users spawn isolated branches. Switching branches swaps the active message history.

**State Management:** Each branch has independent message history. Actions in Branch_B do not affect Branch_A. No sliding window applied—each branch keeps its full history.

**CLI Commands:**
- `/checkpoint <name>` - Save current state as a checkpoint
- `/branch <name>` - Switch to branch (auto-creates if doesn't exist)
- `/branches` - List all available branches

**When to use:**
- A/B testing dialogue scenarios
- Exploratory design sessions
- Content generation with alternatives

**Example:**
```python
agent = DeepSeekAgent(strategy="branching", window_size=6)

# In CLI:
# /checkpoint main           # Save current as "main"
# /branch alternate          # Switch to isolated "alternate" branch
# (continue conversation in alternate)
# /branch main               # Switch back (alternate history preserved)
```

**Debug Output:**
```
[DEBUG - Branching] Created checkpoint: 'main' with 8 messages
[DEBUG - Branching] Switched to branch: 'alternate' (0 messages)
```

---

## Usage

### Installation

Ensure environment variable is set:
```bash
export DEEPSEEK_API_KEY="your_api_key_here"
```

### Running the Agent

```bash
cd task_10
source ../deepseek-env/bin/activate
python main.py
```

### CLI Workflow

1. **Select Strategy** (on startup):
   ```
   Select Context Management Strategy:
     1. Sliding Window
     2. Sticky Facts
     3. Branching
   
   Enter choice (1-3): 2
   ```

2. **Configure Strategy** (if needed):
   ```
   [Configuring sticky_facts]
   Enter window size (default 6): 6
   ```
   (Branching strategy skips this step—uses full history per branch)

3. **Interact**:
   ```
   You: What should be the primary key for our users table?
   
   Agent: The primary key should be a UUID for better...
   
   [Memory State]
     - Messages in window: 2
     - Facts tracked: 5
     - Facts token size: 120
   
   [Token Analytics]
     - User input: 12 tokens
     - Context sent: 145 tokens
     - Completion: 45 tokens
     - Total this turn: 234 tokens
     - Strategy: sticky_facts
   ```

### Available Commands

```
/help                       - Show help
/strategy <name>            - Switch strategy (sliding_window, sticky_facts, branching)
/checkpoint <name>          - Create checkpoint (branching only)
/branch <name>              - Switch to branch (branching only)
/branches                   - List all branches (branching only)
/status                     - Show current strategy status
/exit or /quit              - Exit program
```

### Example Session (Sticky Facts)

```
You: We're building a user management system.

Agent: Great! I'll help you design a user management system...

You: Primary key should be UUID, and we need to track email and phone.

Agent: Perfect. For security, I'd recommend...

[DEBUG - Facts] Updated core facts: {'primary_key': 'UUID', 'fields': ['email', 'phone']}

You: /status
Current Strategy: sticky_facts
Available Branches: N/A

You: /strategy branching
✓ Switched to branching strategy

You: Let's explore an alternative design.

You: /checkpoint original_design
✓ Created checkpoint 'original_design' with 8 messages

You: /branch alternative
✓ Switched to branch 'alternative' (0 messages)

You: What if we used auto-increment instead of UUID?

Agent: Auto-increment would be simpler but...
```

---

## Analytics & Metrics

After every response, metrics are displayed:

```python
{
    "user_input_tokens": 12,
    "context_tokens_before_response": 145,
    "prompt_tokens_used": 167,
    "completion_tokens_used": 45,
    "total_this_step": 212,
    "strategy": "sticky_facts",
    "strategy_debug": {
        "strategy": "sticky_facts",
        "window_size": 6,
        "messages_count": 2,
        "facts_count": 5,
        "facts_tokens": 120,
        "context_size": 7
    }
}
```

---

## Implementation Notes

### Strategy Interface (`ContextStrategy`)

All strategies implement:
- `add_message(role, content)` - Add user/assistant message
- `get_messages_for_api(system_prompt)` - Format messages for API call
- `update_from_response(assistant_response)` - Post-response state update
- `save_state(filepath)` - Persist to disk
- `load_state(filepath)` - Load from disk
- `get_debug_info()` - Return current metrics

### File Persistence

Each strategy saves its state independently:

**Sliding Window:**
```json
{
  "strategy": "sliding_window",
  "messages": [...]
}
```

**Sticky Facts:**
```json
{
  "strategy": "sticky_facts",
  "messages": [...],
  "facts": {"key": "value", ...}
}
```

**Branching:**
```json
{
  "strategy": "branching",
  "messages": [...],
  "current_branch": "main",
  "branches": {
    "main": [...],
    "alternative": [...]
  }
}
```

### Strategy Switching

When switching strategies mid-conversation:
- Messages are transferred to the new strategy
- Sticky facts are preserved if switching to/from `sticky_facts`
- Branches are preserved if switching to/from `branching`
- State is persisted to disk

---

## Test Scenario: 10-Message Conversation

### The Scenario: Database Schema Design

Use this conversation to test all three strategies:

**User Messages (odd numbers) / Assistant Responses (even numbers):**

1. **User:** "We're building an e-commerce platform. Need to store user profiles and orders."
2. **Assistant:** "Great! I'd recommend separating users and orders into different tables. What's your expected user count?"
3. **User:** "We expect 10 million users, with heavy read access for order history."
4. **Assistant:** "10M users requires efficient indexing. I'd suggest UUID primary keys to avoid hotspotting."
5. **User:** "UUID sounds good. Should we include payment information in the orders table?"
6. **Assistant:** "No, store payment info separately for PCI compliance. Use a foreign key reference instead."
7. **User:** "What about soft deletes? Should we track deleted orders?"
8. **Assistant:** "Yes, soft deletes are good for auditing. Add an is_deleted boolean and a deleted_at timestamp."
9. **User:** "How should we handle order statuses? What states should we support?"
10. **Assistant:** "Common states: PENDING, CONFIRMED, SHIPPED, DELIVERED, CANCELLED. Store as enum or separate status table."

---

### Testing Each Strategy

#### Strategy 1: Sliding Window (window_size=4)

**Expected Behavior:**
- Messages 1-6 get evicted as new messages arrive
- By message 10, only messages 7-10 remain in context
- User asking "How should we handle order statuses?" won't have early context (UUID decision, PCI compliance)

**Test in CLI:**
```bash
cd task_10
python main.py
# Select: 1 (Sliding Window)
# Enter window size: 4
# Enter messages 1-10 one by one
# After message 10, check [Memory State] shows only 4 messages
```

**What to verify:**
```
You: Remind me why we chose UUID for the primary key?
[Sliding Window] Cannot answer - message 4 evicted
Agent: (May generate incorrect response without context)
```

---

#### Strategy 2: Sticky Facts (window_size=4)

**Expected Behavior:**
- Only recent messages (7-10) kept in window
- But facts extracted and preserved:
  - `primary_key: UUID`
  - `database_design: separate_users_orders`
  - `payment_storage: separate_table_pci_compliance`
  - `soft_deletes: enabled`
  - `order_statuses: PENDING, CONFIRMED, SHIPPED, DELIVERED, CANCELLED`

**Test in CLI:**
```bash
cd task_10
python main.py
# Select: 2 (Sticky Facts)
# Enter window size: 4
# Enter messages 1-10 one by one
# Watch [DEBUG - Facts] updates after each user message
```

**What to verify:**
```
You: Remind me why we chose UUID for the primary key?
[Sticky Facts] Can answer using preserved facts dictionary
Agent: UUID was chosen to avoid hotspotting with 10M users...
```

**Sample fact evolution:**
```
Turn 1: facts = {}
Turn 3: facts = {"expected_users": "10M", "data_volume": "high_read"}
Turn 5: facts = {..., "primary_key": "UUID"}
Turn 7: facts = {..., "payment_storage": "separate_table_pci"}
Turn 9: facts = {..., "soft_deletes": True, "deleted_timestamp": True}
Turn 10: facts = {..., "order_statuses": ["PENDING", "CONFIRMED", "SHIPPED", "DELIVERED", "CANCELLED"]}
```

---

#### Strategy 3: Branching (window_size not used) - Full Checkpoint & Branch Example

**Scenario:** Create shared history up to checkpoint, then branch to explore alternatives. New messages only added to current branch (shared_history inherited by all).

**Test Workflow in CLI:**

```bash
cd task_10
python main.py
# Select: 3 (Branching)
# (No window size prompt—branching keeps full history per branch)

You: We're building an e-commerce platform. Need to store user profiles and orders.
Agent: Great! I'd recommend...

You: We expect 10 million users, with heavy read access for order history.
Agent: 10M users requires...

You: UUID sounds good. Should we include payment information in the orders table?
Agent: No, store payment info separately...

You: What about soft deletes? Should we track deleted orders?
Agent: Yes, soft deletes are good for auditing...

You: How should we handle order statuses?
Agent: Common states: PENDING, CONFIRMED, SHIPPED, DELIVERED, CANCELLED...

# [10 messages in main. Create checkpoint - moves to shared_history]
You: /checkpoint main_design
[DEBUG - Branching] Created checkpoint: 'main_design' with 10 shared messages
✓ Created checkpoint 'main_design'

# [Branch 1: Denormalization approach (auto-created, inherits shared_history)]
You: /branch branch_denormalized
[DEBUG - Branching] Created new branch: 'branch_denormalized'
[DEBUG - Branching] Switched to branch: 'branch_denormalized' (0 branch messages, 10 shared)
✓ Switched to branch 'branch_denormalized' (creates if new)

You: What if we denormalize for performance? Include payment in orders table?
Agent: Denormalization improves reads but risks PCI compliance...

You: Would that work with our scale?
Agent: At 10M users with denormalization, you'd need careful indexing...

# [Branch 2: Sharding approach (auto-created, inherits shared_history)]
You: /branch branch_sharding
[DEBUG - Branching] Created new branch: 'branch_sharding'
[DEBUG - Branching] Switched to branch: 'branch_sharding' (0 branch messages, 10 shared)
✓ Switched to branch 'branch_sharding' (creates if new)

You: What about horizontal sharding by user_id?
Agent: Sharding is powerful for your scale of 10M users...

You: How do we handle cross-shard analytics queries?
Agent: You'd need a separate analytics database for aggregations...

# [List all branches and switch back to main_design]
You: /branches
Available branches: main_design, branch_denormalized, branch_sharding

You: /branch main_design
[DEBUG - Branching] Switched to branch: 'main_design' (0 branch messages, 10 shared)
✓ Switched to branch 'main_design' (creates if new)

You: Let's stick with the separate tables approach. It's safest.
Agent: Excellent choice! This design is proven and...
```

**Branch Structure Visualization:**
```
shared_history (10 messages) ← available to all branches
├── branch_denormalized [+2 new messages]
└── branch_sharding [+2 new messages]
```

Each branch adds its own messages to the shared history. When accessing branch context, API receives: shared_history + branch_specific_messages.

**State Persistence & Model:**
After `/checkpoint` and `/branch` commands, state is saved to `chat_history.json`:

```json
{
  "strategy": "branching",
  "shared_history": [10 messages from main_design],
  "current_branch": "branch_denormalized",
  "branches": {
    "branch_denormalized": [2 new messages in this branch],
    "branch_sharding": [2 new messages in this branch]
  }
}
```

**How it works:**
- `shared_history`: Messages before all checkpoints (available to all branches)
- `branches[name]`: Only messages added AFTER switching to that branch
- **API payload** = shared_history + current_branch_messages
- Each branch starts empty but inherits full shared history for context

Close and restart the agent—all branches and shared history are restored.

---

### Expected Metrics Output

After each turn, you'll see metrics like:

**Sliding Window (Turn 10):**
```
[Memory State]
  - Messages in window: 4/4

[Token Analytics]
  - User input: 15 tokens
  - Context sent: 98 tokens (only 4 messages)
  - Completion: 42 tokens
  - Total this turn: 155 tokens
```

**Sticky Facts (Turn 10):**
```
[Memory State]
  - Messages in window: 4
  - Facts tracked: 5
  - Facts token size: 156

[Token Analytics]
  - User input: 15 tokens
  - Context sent: 254 tokens (4 messages + facts)
  - Completion: 42 tokens
  - Total this turn: 211 tokens
```

**Branching (After Checkpoint):**
```
[Memory State]
  - Current branch: branch_denormalized
  - Total branches: 2
  - Shared history: 10 messages
  - Messages in current branch: 2

[Token Analytics]
  - User input: 18 tokens
  - Context sent: 340 tokens (10 shared + 2 branch)
  - Completion: 51 tokens
  - Total this turn: 186 tokens
```

---

### Comparison: What Each Strategy Remembers After Turn 10

| Question | Sliding Window | Sticky Facts | Branching |
|----------|---|---|---|
| "Why UUID?" | ❌ Message 4 evicted | ✅ In facts dict | ✅ Full history in main branch |
| "Payment handling?" | ❌ Message 6 evicted | ✅ In facts dict | ✅ Available in main branch |
| "Soft delete states?" | ✅ Message 8 in window | ✅ In facts dict | ✅ Full history in main branch |
| "Order statuses?" | ✅ Message 10 in window | ✅ In facts dict | ✅ Full history in main branch |
| "Explore alternative?" | N/A | N/A | ✅ In separate branch_a |

---

## Comparison & Recommendations

See **COMPARISON.md** for detailed analysis across:
1. **Response Quality** - Accuracy and constraint adherence
2. **Stability** - Risk of forgetting early context
3. **Token Efficiency** - Cost per turn and total cost
4. **User Experience** - Complexity vs. flexibility

### Quick Recommendation Matrix

| Use Case | Strategy | Reason |
|----------|----------|--------|
| Budget-conscious exploration | Sliding Window | Minimal tokens |
| Requirements gathering | Sticky Facts | Preserves constraints |
| A/B design scenarios | Branching | Exploration without loss |
| Long conversations | Sticky Facts | Stable, affordable |
| Interactive prototyping | Branching | Perfect recall |

---

## Files

```
task_10/
├── agent.py           # Refactored DeepSeekAgent with strategy pattern
├── strategies.py      # Strategy implementations
├── main.py            # CLI interface
├── COMPARISON.md      # Detailed strategy comparison
├── README.md          # This file
└── chat_history.json  # Auto-created: persists conversation state
```

---

## Error Handling

The implementation includes robust error handling:
- API failures are caught and reported
- File I/O errors don't crash the agent
- Invalid strategy names are rejected with helpful messages
- Branch switching on non-branching strategies gives clear feedback

Example:
```
Checkpoints are only available in 'branching' strategy
Usage: /strategy <name>
Available: sliding_window, sticky_facts, branching
```

---

## Future Enhancements

Possible extensions:
- Hybrid strategies (e.g., window + facts without background extraction)
- Compression summaries for older messages (like task_6)
- Branch merging (combine two dialogue paths)
- Fact confidence scores
- Multi-file conversation splitting

---

## Testing

To verify the implementation:

1. **Sliding Window:** Message older than window_size should not appear in context
2. **Sticky Facts:** Early constraints should persist even after window eviction
3. **Branching:** Switching branches should restore exact previous state
4. **Token Tracking:** Metrics should match API response usage
5. **Persistence:** Restarting should restore exact previous state

Run test scenarios in `main.py` by creating checkpoints, switching branches, and verifying message recall.
