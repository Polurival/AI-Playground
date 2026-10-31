"""Shared by select_questions.py, teacher.py, filter_data.py, generate.py and score.py:
prompt layout, answer parsing, arithmetic check of a written solution."""
import re

INSTRUCTION = (
    "Solve the math problem step by step. Write the reasoning as short plain-text steps "
    "(no markdown, no LaTeX). The last line must be exactly: Answer: <number>"
)

NUM = r"-?\d[\d,]*(?:\.\d+)?"


def build_prompt(question):
    """The same user message for the teacher, the base student and the tuned student."""
    return f"{question.strip()}\n\n{INSTRUCTION}"


def to_float(s):
    try:
        return float(s.replace(",", "").replace("$", "").rstrip("."))
    except ValueError:
        return None


def gold_answer(answer_field):
    """GSM8K reference: the number after '####'."""
    return to_float(answer_field.split("####")[-1].strip())


def same_number(a, b):
    return a is not None and b is not None and abs(a - b) < 1e-6


STRICT = re.compile(rf"Answer: ({NUM})")


def parse_answer(text):
    """Return (number or None, strict_format_ok).

    strict: the last non-empty line is exactly 'Answer: <number>' and that is the only 'Answer:' in the text.
    Lenient fallback (used for accuracy, so a base model is not punished for style alone):
    'Answer: $18', \\boxed{18}, '#### 18', 'the answer is 18', else the last number in the text.
    """
    t = text.strip()
    lines = [l for l in t.splitlines() if l.strip()]
    if lines:
        m = STRICT.fullmatch(lines[-1].strip())
        if m and t.count("Answer:") == 1:
            return to_float(m.group(1)), True
    for pat in (rf"Answer:\s*\**\s*\$?\s*({NUM})", r"\\boxed\{\s*\\?\$?\s*(" + NUM + r")", rf"####\s*\$?\s*({NUM})",
                rf"(?i:answer is)\s*:?\s*\**\$?\s*({NUM})"):
        found = re.findall(pat, t)
        if found:
            return to_float(found[-1]), False
    found = re.findall(NUM, t)
    return (to_float(found[-1]), False) if found else (None, False)


EQ = re.compile(
    rf"((?:\$?\d[\d,]*(?:\.\d+)?[ \t]*[-+−×*/÷x][ \t]*)+\$?\d[\d,]*(?:\.\d+)?)[ \t]*=[ \t]*\$?({NUM})"
    r"(?![\d%A-Za-z]|[.,]\d|[ \t]*[-+−×*/÷=^(%]|[ \t]*x[ \t]*\d|[ \t]+and[ \t]+\d)")


def bad_equations(text):
    """Equations 'a op b [op c] = r' written in the text whose result is arithmetically wrong.

    Only complete, plain-number equations are judged: skipped when the left side continues an expression
    (preceded by an operator, bracket, letter or digit), the result continues (followed by an operator,
    '=', '%'), integer division with a stated remainder, or the sign of the first number was lost. Rounding is tolerated (rel 1% / abs 0.011).
    Returns a list of the offending strings.
    """
    bad = []
    for m in EQ.finditer(text):
        pre = text[:m.start()]
        if re.search(r"[-−+*/×÷^(]\s*$", pre) or re.search(r"[\w).]$", pre) or re.search(
                r"(\d|\b(times|of|by|plus|minus|and))[ \t]+$", pre):
            continue  # continues a longer expression, a mixed fraction ('16 1/2') or prose ('18 times 2/3')
        left = m.group(1).replace("−", "-").replace("×", "*").replace("÷", "/").replace("$", "").replace(",", "")
        left = re.sub(r"(?<=\d)\s*x\s*(?=\d)", "*", left)
        try:
            val = eval(left, {"__builtins__": {}}, {})  # only digits and + - * / survive the regex
        except Exception:
            continue
        rhs = to_float(m.group(2))
        if rhs is not None and "remainder" in text and rhs == int(val):
            continue  # integer division with a remainder
        if rhs is not None and abs(val - rhs) > max(0.011, 0.01 * abs(val)):
            bad.append(m.group(0).strip())
    return bad


def solution_steps(answer_field):
    """Number of reasoning lines in the GSM8K reference solution (difficulty proxy)."""
    return len([l for l in answer_field.split("####")[0].splitlines() if l.strip()])
