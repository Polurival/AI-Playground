import json
import os
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
import copy


class MemoryLayer(ABC):
    """Base class for memory layers."""

    @abstractmethod
    def save(self, filepath: str) -> None:
        pass

    @abstractmethod
    def load(self, filepath: str) -> bool:
        pass

    @abstractmethod
    def get_debug_info(self) -> Dict[str, Any]:
        pass


class ShortTermMemory(MemoryLayer):
    """Dialogue tree branching - sliding window of last N messages with checkpoint/branch support."""

    def __init__(self, window_size: int = 6):
        self.window_size = window_size
        self.shared_history = []
        self.branches = {}
        self.current_branch = "main"
        self.branches["main"] = []

    def add_message(self, role: str, content: str) -> None:
        """Add message to current branch."""
        self.branches[self.current_branch].append({"role": role, "content": content})

    def get_messages(self) -> List[Dict[str, str]]:
        """Get combined shared history + current branch messages (trimmed to window)."""
        combined = self.shared_history + self.branches[self.current_branch]
        return combined[-self.window_size:] if len(combined) > self.window_size else combined

    def get_all_messages(self) -> List[Dict[str, str]]:
        """Get full untrimmmed history (shared + current branch)."""
        return self.shared_history + self.branches[self.current_branch]

    def create_checkpoint(self, checkpoint_name: str) -> None:
        """Move current branch to shared history, create new empty branch."""
        self.shared_history.extend(self.branches[self.current_branch])
        self.branches[checkpoint_name] = []
        self.current_branch = checkpoint_name
        print(f"[SHORT-TERM] Checkpoint '{checkpoint_name}' created. Shared history: {len(self.shared_history)}")

    def switch_branch(self, branch_name: str) -> bool:
        """Switch to branch (create if not exists)."""
        if branch_name not in self.branches:
            self.branches[branch_name] = []
        self.current_branch = branch_name
        print(f"[SHORT-TERM] Switched to branch '{branch_name}'")
        return True

    def list_branches(self) -> List[str]:
        return list(self.branches.keys())

    def save(self, filepath: str) -> None:
        try:
            data = {
                "layer": "short_term",
                "shared_history": self.shared_history,
                "current_branch": self.current_branch,
                "branches": self.branches
            }
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"Error saving short-term memory: {e}")

    def load(self, filepath: str) -> bool:
        try:
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("layer") == "short_term":
                        self.shared_history = data.get("shared_history", [])
                        self.current_branch = data.get("current_branch", "main")
                        self.branches = data.get("branches", {"main": []})
                        return True
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load short-term memory: {e}")
        return False

    def get_debug_info(self) -> Dict[str, Any]:
        return {
            "current_branch": self.current_branch,
            "branches_count": len(self.branches),
            "shared_history_count": len(self.shared_history),
            "messages_in_current_branch": len(self.branches[self.current_branch]),
            "total_context": len(self.get_all_messages()),
            "window_size": self.window_size,
        }


class WorkingMemory(MemoryLayer):
    """Task context - linear, session-specific."""

    def __init__(self):
        self.task = ""
        self.context = {}
        self.errors = []

    def set_task(self, task_text: str) -> None:
        """Set or overwrite active task."""
        self.task = task_text
        print(f"[WORKING] Task set: {task_text[:50]}...")

    def add_error(self, error: str) -> None:
        """Add error log."""
        self.errors.append(error)

    def add_context(self, key: str, value: Any) -> None:
        """Add context key-value."""
        self.context[key] = value

    def get_context_text(self) -> str:
        """Get formatted context for API."""
        if not self.task and not self.context and not self.errors:
            return ""

        parts = []
        if self.task:
            parts.append(f"Current Task: {self.task}")
        if self.context:
            parts.append(f"Context: {json.dumps(self.context, ensure_ascii=False, indent=2)}")
        if self.errors:
            parts.append(f"Recent Errors: {json.dumps(self.errors[-3:], ensure_ascii=False, indent=2)}")

        return "\n".join(parts)

    def clear(self) -> None:
        """Clear working memory (end of session)."""
        self.task = ""
        self.context = {}
        self.errors = []

    def save(self, filepath: str) -> None:
        try:
            data = {
                "layer": "working",
                "task": self.task,
                "context": self.context,
                "errors": self.errors
            }
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"Error saving working memory: {e}")

    def load(self, filepath: str) -> bool:
        try:
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("layer") == "working":
                        self.task = data.get("task", "")
                        self.context = data.get("context", {})
                        self.errors = data.get("errors", [])
                        return True
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load working memory: {e}")
        return False

    def get_debug_info(self) -> Dict[str, Any]:
        return {
            "has_task": bool(self.task),
            "context_keys": len(self.context),
            "error_count": len(self.errors),
        }


class LongTermMemory(MemoryLayer):
    """User profiles with namespace isolation - permanent constraints & preferences."""

    def __init__(self):
        self.profiles = {}
        self.current_profile = "default"
        self.profiles["default"] = {}

    def switch_profile(self, profile_name: str) -> bool:
        """Switch to profile (create if not exists)."""
        if profile_name not in self.profiles:
            self.profiles[profile_name] = {}
            print(f"[LONG-TERM] Created new profile: '{profile_name}'")
        self.current_profile = profile_name
        print(f"[LONG-TERM] Switched to profile: '{profile_name}'")
        return True

    def remember(self, key: str, value: Any) -> None:
        """Add fact to active profile."""
        self.profiles[self.current_profile][key] = value
        print(f"[LONG-TERM] Profile '{self.current_profile}' updated: {key} = {value}")

    def remember_raw(self, text: str) -> None:
        """Ingest raw text fact into active profile (auto-keyed by timestamp)."""
        import time
        key = f"fact_{int(time.time())}"
        self.profiles[self.current_profile][key] = text
        print(f"[LONG-TERM] Profile '{self.current_profile}' recorded: {text[:50]}...")

    def get_profile_text(self) -> str:
        """Get formatted profile for API."""
        profile = self.profiles[self.current_profile]
        if not profile:
            return ""

        lines = [f"User Profile ({self.current_profile}):"]
        for key, value in profile.items():
            lines.append(f"  - {key}: {value}")
        return "\n".join(lines)

    def list_profiles(self) -> List[str]:
        return list(self.profiles.keys())

    def save(self, filepath: str) -> None:
        try:
            data = {
                "layer": "long_term",
                "current_profile": self.current_profile,
                "profiles": self.profiles
            }
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"Error saving long-term memory: {e}")

    def load(self, filepath: str) -> bool:
        try:
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("layer") == "long_term":
                        self.current_profile = data.get("current_profile", "default")
                        self.profiles = data.get("profiles", {"default": {}})
                        return True
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load long-term memory: {e}")
        return False

    def get_debug_info(self) -> Dict[str, Any]:
        return {
            "current_profile": self.current_profile,
            "profiles_count": len(self.profiles),
            "facts_in_current": len(self.profiles[self.current_profile]),
        }


class MemoryEngine:
    """Three-layer memory management with dynamic context assembly."""

    ASSEMBLY_MODES = {
        "short_only": "System Prompt + Active Short-term Branch",
        "short_working": "Short-term + Working Memory",
        "short_long": "Short-term + Long-term Profile",
        "full_memory": "Short-term + Working + Long-term (Full Assembly)",
    }

    def __init__(self, window_size: int = 6):
        self.short_term = ShortTermMemory(window_size=window_size)
        self.working = WorkingMemory()
        self.long_term = LongTermMemory()
        self.assembly_mode = "full_memory"

    def set_mode(self, mode_name: str) -> bool:
        """Switch assembly mode."""
        if mode_name not in self.ASSEMBLY_MODES:
            print(f"Unknown mode. Available: {', '.join(self.ASSEMBLY_MODES.keys())}")
            return False
        self.assembly_mode = mode_name
        print(f"[ASSEMBLY] Mode set to: {mode_name}")
        return True

    def get_system_messages(self, base_system_prompt: str) -> List[Dict[str, str]]:
        """Build system message list based on assembly mode."""
        messages = [{"role": "system", "content": base_system_prompt}]

        if self.assembly_mode == "short_only":
            pass
        elif self.assembly_mode == "short_working":
            working_text = self.working.get_context_text()
            if working_text:
                messages.append({"role": "system", "content": working_text})
        elif self.assembly_mode == "short_long":
            long_text = self.long_term.get_profile_text()
            if long_text:
                messages.append({"role": "system", "content": long_text})
        elif self.assembly_mode == "full_memory":
            working_text = self.working.get_context_text()
            if working_text:
                messages.append({"role": "system", "content": working_text})
            long_text = self.long_term.get_profile_text()
            if long_text:
                messages.append({"role": "system", "content": long_text})

        return messages

    def get_messages_for_api(self, base_system_prompt: str) -> List[Dict[str, str]]:
        """Assemble final message payload based on mode."""
        messages = self.get_system_messages(base_system_prompt)
        messages.extend(self.short_term.get_messages())
        return messages

    def add_message(self, role: str, content: str) -> None:
        """Add message to short-term only."""
        self.short_term.add_message(role, content)

    def save(self, prefix: str = "") -> None:
        """Persist all layers to disk."""
        self.short_term.save(f"{prefix}short_term.json")
        self.working.save(f"{prefix}working.json")
        self.long_term.save(f"{prefix}long_term.json")

    def load(self, prefix: str = "") -> None:
        """Load all layers from disk."""
        self.short_term.load(f"{prefix}short_term.json")
        self.working.load(f"{prefix}working.json")
        self.long_term.load(f"{prefix}long_term.json")

    def get_debug_info(self) -> Dict[str, Any]:
        return {
            "assembly_mode": self.assembly_mode,
            "short_term": self.short_term.get_debug_info(),
            "working": self.working.get_debug_info(),
            "long_term": self.long_term.get_debug_info(),
        }
