import json
import os
from abc import ABC, abstractmethod
from typing import Tuple, Dict, Any
import tiktoken


class ContextStrategy(ABC):
    """Base class for context management strategies."""

    @abstractmethod
    def add_message(self, role: str, content: str) -> None:
        """Add a message to the strategy's internal state."""
        pass

    @abstractmethod
    def get_messages_for_api(self, system_prompt: str) -> list:
        """Get formatted messages to send to API."""
        pass

    @abstractmethod
    def update_from_response(self, assistant_response: str) -> None:
        """Update internal state after receiving API response."""
        pass

    @abstractmethod
    def save_state(self, filepath: str) -> None:
        """Persist strategy state to disk."""
        pass

    @abstractmethod
    def load_state(self, filepath: str) -> bool:
        """Load strategy state from disk. Return True if loaded, False if not found."""
        pass

    @abstractmethod
    def get_debug_info(self) -> Dict[str, Any]:
        """Return debug information about current state."""
        pass


class SlidingWindowStrategy(ContextStrategy):
    """Keep only last N messages."""

    def __init__(self, window_size: int = 6):
        self.window_size = window_size
        self.messages = []
        self.encoding = tiktoken.get_encoding("cl100k_base")

    def add_message(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})

    def get_messages_for_api(self, system_prompt: str) -> list:
        # Trim to window size if needed
        window = self.messages[-self.window_size:]

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(window)
        return messages

    def update_from_response(self, assistant_response: str) -> None:
        # Check if window exceeded and trim
        if len(self.messages) > self.window_size:
            evicted_count = len(self.messages) - self.window_size
            self.messages = self.messages[-self.window_size:]
            print(f"[DEBUG - Sliding Window] Evicted {evicted_count} old messages")

    def save_state(self, filepath: str) -> None:
        try:
            data = {"strategy": "sliding_window", "messages": self.messages}
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"Error saving sliding window state: {e}")

    def load_state(self, filepath: str) -> bool:
        try:
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("strategy") == "sliding_window":
                        self.messages = data.get("messages", [])
                        return True
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load sliding window state: {e}")
        return False

    def get_debug_info(self) -> Dict[str, Any]:
        return {
            "strategy": "sliding_window",
            "window_size": self.window_size,
            "messages_count": len(self.messages),
            "context_size": len(self.messages),
        }


class StickyFactsStrategy(ContextStrategy):
    """Maintain key-value memory of important facts."""

    def __init__(self, window_size: int = 6):
        self.window_size = window_size
        self.messages = []
        self.facts = {}
        self.encoding = tiktoken.get_encoding("cl100k_base")

    def add_message(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})

    def update_facts(self, client: Any, model: str) -> None:
        """Background API call to extract/update facts from latest user message."""
        if not self.messages or self.messages[-1]["role"] != "user":
            return

        latest_user_msg = self.messages[-1]["content"]

        facts_str = json.dumps(self.facts, ensure_ascii=False, indent=2)
        extraction_prompt = f"""Analyze the following user message and update the key-value facts dictionary.
Keep only factual, actionable information like constraints, preferences, project goals, decisions.
Return ONLY a valid JSON dict with the updated facts.

Current facts: {facts_str}

New user message: {latest_user_msg}

Updated facts (JSON only):"""

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": extraction_prompt}],
                temperature=0.3,
            )

            response_text = response.choices[0].message.content.strip()
            try:
                self.facts = json.loads(response_text)
                print(f"[DEBUG - Facts] Updated core facts: {self.facts}")
            except json.JSONDecodeError:
                print(f"[DEBUG - Facts] Could not parse facts update, keeping existing")
        except Exception as e:
            print(f"[DEBUG - Facts] Background update failed: {e}")

    def get_messages_for_api(self, system_prompt: str) -> list:
        window = self.messages[-self.window_size:]

        facts_str = json.dumps(self.facts, ensure_ascii=False, indent=2) if self.facts else "(none)"

        messages = [{"role": "system", "content": system_prompt}]
        if self.facts:
            messages.append({
                "role": "system",
                "content": f"Core Facts & Constraints:\n{facts_str}"
            })
        messages.extend(window)
        return messages

    def update_from_response(self, assistant_response: str) -> None:
        if len(self.messages) > self.window_size:
            evicted_count = len(self.messages) - self.window_size
            self.messages = self.messages[-self.window_size:]
            print(f"[DEBUG - Sticky Facts] Evicted {evicted_count} old messages (facts preserved)")

    def save_state(self, filepath: str) -> None:
        try:
            data = {
                "strategy": "sticky_facts",
                "messages": self.messages,
                "facts": self.facts
            }
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"Error saving sticky facts state: {e}")

    def load_state(self, filepath: str) -> bool:
        try:
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("strategy") == "sticky_facts":
                        self.messages = data.get("messages", [])
                        self.facts = data.get("facts", {})
                        return True
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load sticky facts state: {e}")
        return False

    def get_debug_info(self) -> Dict[str, Any]:
        facts_tokens = len(self.encoding.encode(json.dumps(self.facts)))
        return {
            "strategy": "sticky_facts",
            "window_size": self.window_size,
            "messages_count": len(self.messages),
            "facts_count": len(self.facts),
            "facts_tokens": facts_tokens,
            "context_size": len(self.messages) + len(self.facts),
        }


class BranchingStrategy(ContextStrategy):
    """Support branching/checkpoints for dialogue trees.

    Model: shared_history (before all checkpoints) + branch-specific messages.
    Each branch starts empty after checkpoint but inherits shared history for API context.
    """

    def __init__(self, window_size: int = 6):
        self.window_size = window_size  # Not used for branching
        self.encoding = tiktoken.get_encoding("cl100k_base")

        # Shared history accessible to all branches
        self.shared_history = []

        # Branch-specific messages
        self.branches = {}  # {branch_name: [messages only in that branch]}
        self.current_branch = "main"
        self.branches["main"] = []

    def add_message(self, role: str, content: str) -> None:
        """Add message to current branch only."""
        self.branches[self.current_branch].append({"role": role, "content": content})

    def get_messages_for_api(self, system_prompt: str) -> list:
        """Return shared history + current branch messages."""
        combined = self.shared_history + self.branches[self.current_branch]
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(combined)
        return messages

    def update_from_response(self, assistant_response: str) -> None:
        # Branching strategy keeps full history per branch - no trimming
        pass

    def create_checkpoint(self, checkpoint_name: str) -> None:
        """Move current branch messages to shared history, create new empty branch."""
        # Merge current branch into shared history
        self.shared_history.extend(self.branches[self.current_branch])

        # Create new branch as empty
        self.branches[checkpoint_name] = []
        self.current_branch = checkpoint_name

        print(f"[DEBUG - Branching] Created checkpoint: '{checkpoint_name}' with {len(self.shared_history)} shared messages")

    def switch_branch(self, branch_name: str) -> bool:
        """Switch to a different branch. Create if doesn't exist."""
        if branch_name not in self.branches:
            # Auto-create new branch with empty messages (inherits shared history)
            self.branches[branch_name] = []
            print(f"[DEBUG - Branching] Created new branch: '{branch_name}'")

        self.current_branch = branch_name
        branch_msg_count = len(self.branches[branch_name])
        total_context = len(self.shared_history) + branch_msg_count
        print(f"[DEBUG - Branching] Switched to branch: '{branch_name}' ({branch_msg_count} branch messages, {len(self.shared_history)} shared)")
        return True

    def list_branches(self) -> list:
        """Return list of available branches."""
        return list(self.branches.keys())

    def save_state(self, filepath: str) -> None:
        try:
            data = {
                "strategy": "branching",
                "shared_history": self.shared_history,
                "current_branch": self.current_branch,
                "branches": self.branches
            }
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"Error saving branching state: {e}")

    def load_state(self, filepath: str) -> bool:
        try:
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("strategy") == "branching":
                        self.shared_history = data.get("shared_history", [])
                        self.current_branch = data.get("current_branch", "main")
                        self.branches = data.get("branches", {"main": []})
                        return True
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load branching state: {e}")
        return False

    def get_debug_info(self) -> Dict[str, Any]:
        branch_msg_count = len(self.branches[self.current_branch])
        total_context = len(self.shared_history) + branch_msg_count
        return {
            "strategy": "branching",
            "current_branch": self.current_branch,
            "branches_count": len(self.branches),
            "shared_history_count": len(self.shared_history),
            "messages_in_current_branch": branch_msg_count,
            "context_size": total_context,
        }
