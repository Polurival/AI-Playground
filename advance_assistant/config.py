"""Configuration for the general assistant.

Standalone (like `week_7_PR_autoreview`): no sys.path tricks into other weeks. Depends only on
`openai` + `mcp`. All knobs are env-driven so the same code runs against DeepSeek (default),
OpenAI, or any OpenAI-compatible gateway.
"""

from dataclasses import dataclass
import os


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass
class AssistantConfig:
    """One assistant session: where files live, model settings, loop budget."""

    workspace: str = ""                 # directory the file tools are confined to
    read_only: bool = False             # True = file-writing tools are not offered at all
    max_steps: int = 10                 # max tool-call rounds per user message
    max_tokens: int = 1800
    temperature: float = 0.3
    llm_model: str = _env("ASSISTANT_LLM_MODEL", "deepseek-chat")
    llm_base_url: str = _env("ASSISTANT_LLM_BASE_URL", "https://api.deepseek.com")
    lang: str = _env("ASSISTANT_LANG", "ru")    # language of replies: "ru" or "en"

    def __post_init__(self) -> None:
        if not self.workspace:
            self.workspace = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workspace")
        self.workspace = os.path.abspath(os.path.expanduser(self.workspace))
        os.makedirs(self.workspace, exist_ok=True)

    @property
    def llm_api_key(self) -> str | None:
        return (
            os.environ.get("ASSISTANT_LLM_API_KEY")
            or os.environ.get("DEEPSEEK_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
        )
