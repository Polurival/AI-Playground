import os
import json
from openai import OpenAI
import tiktoken
from typing import Tuple, Dict, Any, Optional
from strategies import (
    ContextStrategy,
    SlidingWindowStrategy,
    StickyFactsStrategy,
    BranchingStrategy
)


class DeepSeekAgent:
    """
    Refactored agent supporting multiple context management strategies.
    Supports Sliding Window, Sticky Facts, and Branching strategies.
    """

    STRATEGIES = {
        "sliding_window": SlidingWindowStrategy,
        "sticky_facts": StickyFactsStrategy,
        "branching": BranchingStrategy,
    }

    def __init__(
        self,
        strategy: str = "sliding_window",
        system_prompt: Optional[str] = None,
        history_file: str = "chat_history.json",
        window_size: int = 6
    ):
        """
        Initialize the agent with a specific context strategy.

        Args:
            strategy: One of 'sliding_window', 'sticky_facts', 'branching'
            system_prompt: System prompt for the model
            history_file: Path to save conversation state
            window_size: Number of messages to retain (for sliding_window and sticky_facts)
        """
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY environment variable not set. "
                "Set it before running this script."
            )

        if strategy not in self.STRATEGIES:
            raise ValueError(f"Unknown strategy: {strategy}. Choose from {list(self.STRATEGIES.keys())}")

        self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        self.model = "deepseek-v4-flash"
        self.history_file = history_file
        self.default_system_prompt = (
            system_prompt or
            "You are a helpful assistant. Respond concisely and directly."
        )
        self.encoding = tiktoken.get_encoding("cl100k_base")

        # Initialize strategy
        self.strategy_name = strategy
        self.strategy: ContextStrategy = self.STRATEGIES[strategy](window_size=window_size)

        # Load existing state if available
        self._load_history()

    def _load_history(self) -> None:
        """Load conversation state from disk if it exists."""
        try:
            if os.path.exists(self.history_file):
                self.strategy.load_state(self.history_file)
                print(f"✓ Loaded {self.strategy_name} state from {self.history_file}")
            else:
                print(f"✓ Starting fresh {self.strategy_name} conversation")
        except Exception as e:
            print(f"Warning: Could not load history: {e}")

    def _save_history(self) -> None:
        """Persist current state to disk."""
        try:
            self.strategy.save_state(self.history_file)
        except Exception as e:
            print(f"Error: Could not save history: {e}")

    def _count_tokens(self, messages: list) -> int:
        """Count tokens in a message list."""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            tokens = len(self.encoding.encode(content))
            total += tokens
        return total

    def _update_facts_if_needed(self) -> None:
        """Background facts update for sticky_facts strategy."""
        if isinstance(self.strategy, StickyFactsStrategy):
            self.strategy.update_facts(self.client, self.model)

    def send_message(self, user_text: str) -> Tuple[str, Dict[str, Any]]:
        """
        Send a message and get a response.

        Args:
            user_text: User's input

        Returns:
            Tuple of (response_text, metrics_dict)
        """
        # Track tokens for user input
        user_tokens = len(self.encoding.encode(user_text))

        # Add user message to strategy
        self.strategy.add_message("user", user_text)

        # Update facts asynchronously if using sticky_facts
        self._update_facts_if_needed()

        # Get messages formatted for API
        messages_for_api = self.strategy.get_messages_for_api(self.default_system_prompt)

        # Count context tokens
        context_tokens = self._count_tokens(messages_for_api)

        # Call API
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages_for_api
            )

            assistant_response = response.choices[0].message.content
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens

            # Add assistant response to strategy
            self.strategy.add_message("assistant", assistant_response)

            # Update internal state after response
            self.strategy.update_from_response(assistant_response)

            # Save state
            self._save_history()

            # Build metrics
            debug_info = self.strategy.get_debug_info()
            metrics = {
                "user_input_tokens": user_tokens,
                "context_tokens_before_response": context_tokens,
                "prompt_tokens_used": prompt_tokens,
                "completion_tokens_used": completion_tokens,
                "total_this_step": prompt_tokens + completion_tokens,
                "strategy": self.strategy_name,
                "strategy_debug": debug_info,
            }

            return assistant_response, metrics

        except Exception as e:
            print(f"API Error: {e}")
            raise

    def switch_strategy(self, new_strategy: str, window_size: int = 6) -> bool:
        """
        Switch to a different context strategy.

        Args:
            new_strategy: Strategy name
            window_size: Window size for the new strategy

        Returns:
            True if switch successful, False otherwise
        """
        if new_strategy not in self.STRATEGIES:
            print(f"Unknown strategy: {new_strategy}")
            return False

        if new_strategy == self.strategy_name:
            print(f"Already using {new_strategy} strategy")
            return True

        # Save current state
        self._save_history()

        # Create new strategy and copy messages if possible
        old_strategy = self.strategy
        new_strategy_instance = self.STRATEGIES[new_strategy](window_size=window_size)

        # Transfer messages to new strategy
        if hasattr(old_strategy, 'messages'):
            for msg in old_strategy.messages:
                new_strategy_instance.add_message(msg["role"], msg["content"])

        # If switching to sticky_facts, transfer facts
        if new_strategy == "sticky_facts" and isinstance(old_strategy, StickyFactsStrategy):
            new_strategy_instance.facts = old_strategy.facts.copy()

        # If switching to branching, transfer branches
        if new_strategy == "branching" and isinstance(old_strategy, BranchingStrategy):
            new_strategy_instance.branches = old_strategy.branches.copy()
            new_strategy_instance.current_branch = old_strategy.current_branch

        self.strategy = new_strategy_instance
        self.strategy_name = new_strategy
        self._save_history()

        print(f"[DEBUG] Switched from {old_strategy.__class__.__name__} to {new_strategy_instance.__class__.__name__}")
        return True

    def create_checkpoint(self, checkpoint_name: str) -> bool:
        """Create a checkpoint (for branching strategy)."""
        if not isinstance(self.strategy, BranchingStrategy):
            print("Checkpoints are only available in 'branching' strategy")
            return False
        self.strategy.create_checkpoint(checkpoint_name)
        self._save_history()
        return True

    def switch_branch(self, branch_name: str) -> bool:
        """Switch to a different branch (for branching strategy)."""
        if not isinstance(self.strategy, BranchingStrategy):
            print("Branches are only available in 'branching' strategy")
            return False
        result = self.strategy.switch_branch(branch_name)
        if result:
            self._save_history()
        return result

    def list_branches(self) -> Optional[list]:
        """List available branches (for branching strategy)."""
        if not isinstance(self.strategy, BranchingStrategy):
            return None
        return self.strategy.list_branches()

    def get_current_strategy(self) -> str:
        """Return the name of the current strategy."""
        return self.strategy_name
