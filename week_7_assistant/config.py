"""Project-agnostic configuration for the developer assistant.

Everything that is specific to *which* project the assistant serves lives here as data, not
as hardcoded paths in the pipeline. Point the assistant at a different repo by building a new
`ProjectConfig` (or passing `--repo` on the CLI) — no code changes required.
"""

from dataclasses import dataclass, field
import os


# Default glob patterns (relative to the repo root) that make up the RAG corpus. Covers the
# three source types the assignment asks for: README, project/docs, and any schema/API markdown.
DEFAULT_DOC_GLOBS: list[str] = [
    "README*",
    "readme*",
    "docs/**/*.md",
    "docs/**/*.rst",
    "docs/**/*.txt",
    "**/*.schema.json",
    "openapi*.json",
    "openapi*.yaml",
]

# Files we never want in the corpus even if a glob catches them.
DEFAULT_EXCLUDE_DIRS: set[str] = {".git", "node_modules", "__pycache__", ".venv", "venv", "site"}


@dataclass
class ProjectConfig:
    """Describes one target project the assistant can answer questions about."""

    repo_path: str                                  # absolute path to the target git repo on disk
    name: str = ""                                  # human label, e.g. "Typer"; defaults to repo dir name
    db_path: str = ""                               # sqlite file holding this project's doc embeddings
    table: str = "doc_chunks"                       # table name inside the db
    doc_globs: list[str] = field(default_factory=lambda: list(DEFAULT_DOC_GLOBS))
    exclude_dirs: set[str] = field(default_factory=lambda: set(DEFAULT_EXCLUDE_DIRS))

    def __post_init__(self) -> None:
        self.repo_path = os.path.abspath(os.path.expanduser(self.repo_path))
        if not self.name:
            self.name = os.path.basename(self.repo_path.rstrip("/")) or "project"
        if not self.db_path:
            # Store the index next to this package, keyed by project name, so re-ingesting one
            # project never clobbers another.
            here = os.path.dirname(os.path.abspath(__file__))
            self.db_path = os.path.join(here, f"rag_{self.name}.db")
