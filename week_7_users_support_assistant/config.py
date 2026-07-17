"""Configuration for the user-support assistant.

Everything product-specific is data, not hardcoded paths in the pipeline: the documentation
corpus (`product_dir` + globs), the CRM store the MCP server reads (`crm_dir`), and the vector
index (`db_path`). Serving a different product = building a different `SupportConfig`.

The defaults describe the demo product bundled with this package: TaskPilot, a fictional SaaS
(see SPEC.md §3), with a synthetic CRM in `crm_data/`.
"""

from dataclasses import dataclass, field
import os

_HERE = os.path.dirname(os.path.abspath(__file__))

# The RAG corpus: product overview + FAQ + docs. Same three source types a real product has.
DEFAULT_DOC_GLOBS: list[str] = [
    "README*",
    "docs/**/*.md",
    "docs/**/*.txt",
]

DEFAULT_EXCLUDE_DIRS: set[str] = {".git", "__pycache__", ".venv", "venv", "node_modules"}


@dataclass
class SupportConfig:
    """Describes one product the support assistant serves."""

    product_name: str = "TaskPilot"
    product_dir: str = os.path.join(_HERE, "product")   # documentation corpus root
    crm_dir: str = os.path.join(_HERE, "crm_data")      # users.json + tickets.json (read via MCP)
    db_path: str = ""                                   # sqlite index of doc embeddings
    table: str = "doc_chunks"
    doc_globs: list[str] = field(default_factory=lambda: list(DEFAULT_DOC_GLOBS))
    exclude_dirs: set[str] = field(default_factory=lambda: set(DEFAULT_EXCLUDE_DIRS))

    def __post_init__(self) -> None:
        self.product_dir = os.path.abspath(os.path.expanduser(self.product_dir))
        self.crm_dir = os.path.abspath(os.path.expanduser(self.crm_dir))
        if not self.db_path:
            # Keyed by product so indexing a second product never clobbers the first.
            slug = self.product_name.lower().replace(" ", "_")
            self.db_path = os.path.join(_HERE, f"rag_{slug}.db")
