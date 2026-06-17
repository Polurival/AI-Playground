import os
from openai import OpenAI
import tiktoken
from typing import Tuple, Dict, Any, Optional
from memory import MemoryEngine


class DeepSeekAgent:
    """Multi-layer memory agent with dynamic context assembly."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        system_prompt: Optional[str] = None,
        window_size: int = 6,
        memory_dir: str = ".memory"
    ):
        api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY environment variable not set")

        self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        self.model = "deepseek-v4-flash"
        self.system_prompt = system_prompt or "You are a helpful assistant. Respond concisely and directly."
        self.encoding = tiktoken.get_encoding("cl100k_base")

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
