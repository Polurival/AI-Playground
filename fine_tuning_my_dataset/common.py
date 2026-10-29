"""Shared by prepare_data.py, generate.py and score.py: prompt layout and answer parsing."""
import re
import unicodedata

LETTERS = "ABCD"

# Prompt with instructions + 3 hand-written shots (none of them is in questions.json).
SYSTEM_PROMPT = (
    "Eres un experto en historia, geografía y cultura de México que resuelve preguntas de opción múltiple.\n"
    "Reglas:\n"
    "1. Elige exactamente UNA opción: la correcta (A, B, C o D).\n"
    "2. Responde SOLO con una línea con este formato exacto: Respuesta: <LETRA>) <texto de la opción>\n"
    "3. No expliques, no añadas nada antes ni después, no uses negritas ni otro idioma que no sea español."
)
FEWSHOT = [
    ("¿En qué año se promulgó la Constitución vigente de México?",
     ["1810", "1917", "1857", "1960"], 1),
    ("¿Cuál es el río más largo que atraviesa la frontera norte de México?",
     ["Río Grijalva", "Río Lerma", "Río Bravo", "Río Papaloapan"], 2),
    ("¿Quién pintó el mural «Sueño de una tarde dominical en la Alameda Central»?",
     ["Diego Rivera", "David Alfaro Siqueiros", "José Clemente Orozco", "Rufino Tamayo"], 0),
]


def format_question(question, options):
    return question + "\n" + "\n".join(f"{LETTERS[i]}) {o}" for i, o in enumerate(options))


def format_answer(options, idx):
    return f"Respuesta: {LETTERS[idx]}) {options[idx]}"


def prompted_messages(question, options):
    """Chat history for the 'good prompt' baseline: system rules + few-shot turns + the real question."""
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    for q, opts, idx in FEWSHOT:
        msgs += [{"role": "user", "content": format_question(q, opts)},
                 {"role": "assistant", "content": format_answer(opts, idx)}]
    msgs.append({"role": "user", "content": format_question(question, options)})
    return msgs


def plain_messages(question, options):
    """Bare question + options, no instructions: what the tuned model is trained on."""
    return [{"role": "user", "content": format_question(question, options)}]


def norm(s):
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", s).split())


STRICT = re.compile(r"Respuesta: ([ABCD])\) (.+)")


def parse_answer(text, options):
    """Return (letter_idx or None, strict_format_ok).

    strict: the whole reply is exactly one line 'Respuesta: X) <text of option X>'.
    Lenient (used for accuracy, so a base model is not punished for style alone): 'Respuesta: X',
    'answer is X', a leading 'X)', **X**, or a reply that contains exactly one option's text.
    """
    t = text.strip()
    m = STRICT.fullmatch(t)
    if m and "\n" not in t and norm(m.group(2)) == norm(options[LETTERS.index(m.group(1))]):
        return LETTERS.index(m.group(1)), True
    for pat in (r"(?i:respuesta)[^A-Za-z]{0,12}\b([A-D])\b",
                r"(?i:answer|correct option|opci[oó]n correcta)[^A-Za-z]{0,12}(?i:is|es)?\W*\b([A-D])\b",
                r"^\W{0,3}([A-D])\s*[\).:]", r"\*\*([A-D])\*\*"):
        m = re.search(pat, t, re.M)
        if m:
            return LETTERS.index(m.group(1)), False
    hits = [i for i, o in enumerate(options) if norm(o) and norm(o) in norm(t)]
    return (hits[0], False) if len(hits) == 1 else (None, False)
