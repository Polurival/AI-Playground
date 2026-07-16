"""Configuration for the PR auto-reviewer.

Everything project-specific is data here, not hardcoded in the pipeline, so the reviewer can be
pointed at ANY git repository (`--repo` on the CLI, or the checked-out repo in CI) without code
changes. Defaults are read from the environment so the same code runs unchanged locally and inside
a GitHub Action.

The reviewer is deliberately standalone (unlike `week_7_assistant`, which reuses the week_5 RAG
engines over `sys.path`): the whole point of this package is to be droppable into any repo, so it
carries its own tiny vector store, cosine search, CPU embeddings, and OpenAI-compatible LLM client
and depends only on `openai` + `sentence-transformers`.
"""

from dataclasses import dataclass, field
import os


# --- RAG corpus (documentation + code) ------------------------------------------------------------
# The assignment asks the reviewer to use RAG over "documentation + code", so the corpus is both.
DOC_EXTS: set[str] = {".md", ".rst", ".txt", ".adoc"}
CODE_EXTS: set[str] = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".kt", ".scala",
    ".rb", ".php", ".c", ".h", ".cc", ".cpp", ".hpp", ".cs", ".swift", ".sh", ".bash",
    ".sql", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".gradle", ".vue", ".svelte",
}
# Files with no extension that are still worth indexing (docs by convention).
DOC_BASENAMES: set[str] = {"README", "readme", "CHANGELOG", "CONTRIBUTING", "ARCHITECTURE"}

# Directories that never belong in the corpus, even if they contain matching files.
DEFAULT_EXCLUDE_DIRS: set[str] = {
    ".git", ".github", "node_modules", "__pycache__", ".venv", "venv", "env",
    "deepseek-env", "hf-env", "dist", "build", "site", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".idea", ".vscode", "target", "vendor", ".next", "coverage",
}
# File suffixes to always skip (generated / binary / vendored).
DEFAULT_EXCLUDE_SUFFIXES: set[str] = {
    ".db", ".sqlite", ".sqlite3", ".lock", ".min.js", ".map", ".png", ".jpg", ".jpeg",
    ".gif", ".svg", ".ico", ".pdf", ".zip", ".gz", ".woff", ".woff2", ".ttf",
}

MAX_FILE_BYTES = 200_000        # skip files bigger than this (huge generated/data files)
CHUNK_CHARS = 1_500             # target chunk size for both docs and code
CHUNK_OVERLAP = 200             # overlap between adjacent chunks so a boundary fact isn't lost


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass
class ReviewConfig:
    """Describes one review run: which repo, where the index lives, and the model settings."""

    repo_path: str                                   # absolute path to the repo being reviewed
    name: str = ""                                   # human label; defaults to repo dir name
    db_path: str = ""                                # sqlite index for this repo's corpus
    exclude_dirs: set[str] = field(default_factory=lambda: set(DEFAULT_EXCLUDE_DIRS))
    exclude_suffixes: set[str] = field(default_factory=lambda: set(DEFAULT_EXCLUDE_SUFFIXES))

    # Retrieval knobs.
    top_k_per_file: int = int(_env("AUTOREVIEW_TOP_K", "4"))     # chunks retrieved per changed file
    max_context_chunks: int = int(_env("AUTOREVIEW_MAX_CTX", "10"))  # cap after de-dup across files
    max_diff_chars: int = int(_env("AUTOREVIEW_MAX_DIFF", "16000"))  # per-PR diff budget in the prompt

    # Model settings (all env-driven; defaults target DeepSeek, an OpenAI-compatible endpoint).
    embed_model: str = _env("AUTOREVIEW_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    llm_model: str = _env("AUTOREVIEW_LLM_MODEL", "deepseek-chat")
    llm_base_url: str = _env("AUTOREVIEW_LLM_BASE_URL", "https://api.deepseek.com")
    review_lang: str = _env("AUTOREVIEW_LANG", "ru")             # "ru" or "en"

    def __post_init__(self) -> None:
        self.repo_path = os.path.abspath(os.path.expanduser(self.repo_path))
        if not self.name:
            self.name = os.path.basename(self.repo_path.rstrip("/")) or "project"
        if not self.db_path:
            here = os.path.dirname(os.path.abspath(__file__))
            self.db_path = os.path.join(here, f"index_{self.name}.db")

    @property
    def llm_api_key(self) -> str | None:
        """The API key for the LLM endpoint. Accepts a generic key or the provider-specific ones so
        the same code works against DeepSeek, OpenAI, or any OpenAI-compatible gateway."""
        return (
            os.environ.get("AUTOREVIEW_LLM_API_KEY")
            or os.environ.get("DEEPSEEK_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
        )
