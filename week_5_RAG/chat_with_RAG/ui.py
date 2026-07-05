"""Terminal colouring: a logging formatter that tints each RAG/state stage by its tag, plus
small helpers to render the structured answer and the TaskState panel nicely in the CLI."""

import logging
import sys

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
GREY = "\033[90m"
BRIGHT_MAGENTA = "\033[95m"
BRIGHT_GREEN = "\033[92m"
BRIGHT_CYAN = "\033[96m"

# stage tag (substring in the log message) -> colour
_TAG_COLORS = {
    "[STATE]": BRIGHT_MAGENTA,
    "[REWRITE]": CYAN,
    "[RETRIEVE]": BLUE,
    "[THRESHOLD]": YELLOW,
    "[RERANK]": MAGENTA,
    "[GENERATE-v3]": GREEN,
    "[CHAT]": BOLD + GREEN,
    "[REFUSAL]": RED,
}


class ColorFormatter(logging.Formatter):
    """Colourises a log line based on the first known stage tag it contains."""

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        color = ""
        for tag, c in _TAG_COLORS.items():
            if tag in record.getMessage():
                color = c
                break
        if not color and record.levelno >= logging.WARNING:
            color = RED
        return f"{color}{msg}{RESET}" if color else msg


def setup_logging(level: int = logging.INFO) -> None:
    """Route all module loggers (including the reused RAG modules) through the colour handler."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ColorFormatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def rule(char: str = "=", width: int = 90, color: str = GREY) -> str:
    return f"{color}{char * width}{RESET}"


def render_answer(answer: str) -> str:
    """Colour the ## Answer / ## Quotes Used / ## Sources headings for readability."""
    out = []
    for line in answer.splitlines():
        stripped = line.strip()
        if stripped.startswith("## Answer"):
            out.append(f"{BOLD}{BRIGHT_GREEN}{line}{RESET}")
        elif stripped.startswith("## Quotes Used"):
            out.append(f"{BOLD}{BRIGHT_CYAN}{line}{RESET}")
        elif stripped.startswith("## Sources"):
            out.append(f"{BOLD}{YELLOW}{line}{RESET}")
        else:
            out.append(line)
    return "\n".join(out)


def render_task_state(state: dict) -> str:
    """Compact coloured panel of the current TaskState."""
    def block(title: str, items: list) -> str:
        head = f"{BOLD}{BRIGHT_MAGENTA}{title}{RESET}"
        if not items:
            return f"{head}\n  {DIM}(none yet){RESET}"
        body = "\n".join(f"  {MAGENTA}•{RESET} {it}" for it in items)
        return f"{head}\n{body}"

    lines = [
        f"{BOLD}{BRIGHT_MAGENTA}╭─ TASK STATE (sticky memory) ─────────────────────────────{RESET}",
        block("Goals", state.get("goals", [])),
        block("Constraints & fixed terms", state.get("constraints_and_terms", [])),
        block("User clarifications", state.get("user_clarifications", [])),
        f"{BOLD}{BRIGHT_MAGENTA}╰──────────────────────────────────────────────────────────{RESET}",
    ]
    return "\n".join(lines)
