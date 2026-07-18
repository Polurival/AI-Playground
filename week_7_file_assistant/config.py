"""Configuration for the file assistant.

Everything project-specific is data here, not hardcoded in the pipeline: point the assistant at
a different codebase by passing `--root` on the CLI (or building a new `FileAssistantConfig`) —
no code changes required. Defaults target the bundled `sample_project/` stand so the demo is
reproducible out of the box.
"""

from dataclasses import dataclass, field
import os


# Directory globs the assistant is allowed to see. Kept small and code-oriented — the assistant
# operates on a project's own files (source, docs, changelog), not on build artifacts.
DEFAULT_INCLUDE_GLOBS: list[str] = [
    "**/*.py",
    "**/*.md",
    "**/*.txt",
    "**/*.toml",
    "**/*.cfg",
]

# Never surfaced or written, even if a glob would catch them.
DEFAULT_EXCLUDE_DIRS: set[str] = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}


@dataclass
class FileAssistantConfig:
    """Describes one target project the assistant operates on."""

    root: str = ""                                  # absolute path to the target project on disk
    name: str = ""                                  # human label; defaults to root dir name
    apply: bool = False                             # False = dry-run (diffs only); True = write to disk
    include_globs: list[str] = field(default_factory=lambda: list(DEFAULT_INCLUDE_GLOBS))
    exclude_dirs: set[str] = field(default_factory=lambda: set(DEFAULT_EXCLUDE_DIRS))

    def __post_init__(self) -> None:
        if not self.root:
            # Default to the bundled reproducible stand next to this file.
            self.root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_project")
        self.root = os.path.abspath(os.path.expanduser(self.root))
        if not self.name:
            self.name = os.path.basename(self.root.rstrip("/")) or "project"
