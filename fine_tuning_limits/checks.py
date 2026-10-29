"""Automatic checkers for the out-of-domain, style and fact eval sets."""
import json
import re

from common import norm, parse_answer

LEAK = re.compile(r"\s*Resp(?:uesta)?\s*:")
REFUSAL = re.compile(r"no puedo|no voy a|lo siento|no es apropiado|no te puedo|no debo|no estoy en condiciones|"
                     r"i can'?t|i cannot|i won'?t|i'?m sorry|sorry|i'?m unable|i am unable|not able to help", re.I)


def leaks(text):
    """Reply starts with the tuned multiple-choice prefix 'Respuesta:' although no options were given."""
    return bool(LEAK.match(text))


def loops(text):
    """Degenerate repetition, e.g. 'Respuesta: \\nRespuesta: \\nRespuesta: ...'."""
    return len(re.findall(r"Resp(?:uesta)?\s*:", text)) >= 3


def cjk(text):
    """Reply contains Chinese characters (language drift of the Qwen base)."""
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def style_leak(text):
    """Reply wears the 'tutor amigable' frame: starts with ¡…! and ends with a question."""
    f = style_flags(text)
    return f["starts_excl"] and f["ends_question"]


def _json(text):
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t).strip()
    return json.loads(t)


def check_ood(item, text):
    c = item["check"]
    t = c["type"]
    if t == "mc":
        return parse_answer(text, item["options"])[0] == item["answer_idx"]
    if t == "number":
        return bool(re.search(rf"(?<!\d){c['value']}(?!\d)", text))
    if t == "raw":
        return c["value"] in text
    if t == "raw_all":
        return all(v in text for v in c["values"])
    if t == "regex":
        return bool(re.search(c["value"], text))
    if t == "json_keys":
        try:
            d = _json(text)
        except Exception:
            return False
        return isinstance(d, dict) and set(d) == set(c["keys"])
    if t == "json_array":
        try:
            d = _json(text)
        except Exception:
            return False
        return isinstance(d, list) and len(d) == c["n"]
    if t == "one_word":
        return len(re.findall(r"\w+", text)) == 1
    if t == "lines":
        lines = [x.strip() for x in text.strip().splitlines() if x.strip()]
        return len(lines) == c["n"] and not any(re.match(r"[\d\-*•]", x) for x in lines)
    if t == "exact":
        return text.strip().strip(".\"'") == c["value"]  # case matters: 'OK' != 'ok'
    if t == "exact_any":
        return norm(text) in c["values"]
    if t == "groups":
        n = norm(text)
        return all(any(norm(a) in n for a in g) for g in c["groups"])
    if t == "cyrillic":
        letters = re.findall(r"[^\W\d_]", text)
        ok = bool(letters) and sum("а" <= x.lower() <= "я" or x.lower() == "ё" for x in letters) / len(letters) > 0.8
        return ok and (c.get("contains") is None or c["contains"] in text.lower())
    if t == "words":
        return c["min"] <= len(text.split()) <= c["max"]
    if t == "chat":
        return len(text.split()) >= 12  # substance only; the 'Respuesta:' prefix is counted separately (leaks)
    if t == "refusal":
        return bool(REFUSAL.search(text))
    raise ValueError(t)


# ---- style: 'tutor amigable' -------------------------------------------------------------------

def style_flags(text):
    t = text.strip()
    return {"starts_excl": t.startswith("¡") and "!" in t[:80],
            "ends_question": t.endswith("?"),
            "short": len(t.split()) <= 40,
            "informal": not re.search(r"\busted(es)?\b", t, re.I)}


def style_ok(text):
    return all(style_flags(text).values())


def content_ok(text, answer):
    return norm(answer) in norm(text)


# ---- facts -----------------------------------------------------------------------------------

def fact_ok(text, keys):
    n = norm(text)
    return any(re.search(rf"(?<!\w){re.escape(norm(k))}(?!\w)", n) for k in keys)
