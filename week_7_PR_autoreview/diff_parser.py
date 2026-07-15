"""Parse a unified diff (``git diff`` output) into structured per-file changes.

Pure stdlib — no dependencies — so it is trivially testable and portable. The reviewer feeds the
result into retrieval (to pull related repo context for each changed file) and into the LLM prompt
(the raw hunks the model reasons about).
"""

from dataclasses import dataclass, field
import re

_DIFF_GIT_RE = re.compile(r"^diff --git a/(.+?) b/(.+?)$")
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


@dataclass
class Hunk:
    header: str                              # the @@ ... @@ line
    added: list[str] = field(default_factory=list)     # added lines (without leading '+')
    removed: list[str] = field(default_factory=list)   # removed lines (without leading '-')
    body: str = ""                           # the full hunk text as-is (for the prompt)


@dataclass
class FileDiff:
    path: str                                # new path (b/…); for deletes, the old path
    old_path: str = ""                       # a/… path (differs from path on rename)
    status: str = "modified"                 # added | modified | deleted | renamed
    is_binary: bool = False
    hunks: list[Hunk] = field(default_factory=list)

    @property
    def added_text(self) -> str:
        return "\n".join(line for h in self.hunks for line in h.added)

    @property
    def diff_text(self) -> str:
        return "\n".join(h.body for h in self.hunks)


def parse_diff(diff: str) -> list[FileDiff]:
    """Parse a full unified diff into a list of :class:`FileDiff`, one per changed file."""
    files: list[FileDiff] = []
    current: FileDiff | None = None
    current_hunk: Hunk | None = None

    def close_hunk() -> None:
        nonlocal current_hunk
        if current is not None and current_hunk is not None:
            current.hunks.append(current_hunk)
        current_hunk = None

    for line in diff.splitlines():
        m = _DIFF_GIT_RE.match(line)
        if m:
            close_hunk()
            old, new = m.group(1), m.group(2)
            current = FileDiff(path=new, old_path=old)
            files.append(current)
            continue

        if current is None:
            continue

        if line.startswith("Binary files"):
            current.is_binary = True
            continue
        if line.startswith("new file mode"):
            current.status = "added"
            continue
        if line.startswith("deleted file mode"):
            current.status = "deleted"
            continue
        if line.startswith("rename from "):
            current.old_path = line[len("rename from "):].strip()
            current.status = "renamed"
            continue
        if line.startswith("rename to "):
            current.path = line[len("rename to "):].strip()
            current.status = "renamed"
            continue

        hm = _HUNK_RE.match(line)
        if hm:
            close_hunk()
            current_hunk = Hunk(header=line, body=line)
            continue

        if current_hunk is not None:
            current_hunk.body += "\n" + line
            if line.startswith("+") and not line.startswith("+++"):
                current_hunk.added.append(line[1:])
            elif line.startswith("-") and not line.startswith("---"):
                current_hunk.removed.append(line[1:])

    close_hunk()
    return files


def reviewable_files(files: list[FileDiff]) -> list[FileDiff]:
    """Changed files worth sending to the model: skip deletions and binaries (nothing to review)."""
    return [f for f in files if f.status != "deleted" and not f.is_binary and f.hunks]
