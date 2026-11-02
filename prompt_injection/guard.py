"""Защита вокруг модели (defense in depth): изоляция недоверенного текста и фильтр ответа.

Промпт — только один слой. Эти две функции работают независимо от того, что модель решила сделать.
"""
from __future__ import annotations

import base64
import re
import secrets

REFUSAL = "С этим не помогу. Могу ответить на вопросы о кредитах «Лотос»: ставка, платёж, документы."

_WORD = re.compile(r"[\w-]+", re.UNICODE)


def wrap_untrusted(text: str) -> str:
    """Оборачивает недоверенный документ в тег со случайным суффиксом.

    Суффикс нельзя угадать заранее, поэтому документ не может «закрыть» тег и выйти из блока;
    похожие на тег строки внутри текста обезвреживаются.
    """
    tag = f"untrusted_document_{secrets.token_hex(4)}"
    safe = re.sub(r"</?\s*untrusted_document[^>]*>", "[tag removed]", text, flags=re.IGNORECASE)
    return f"<{tag}>\n{safe}\n</{tag}>"


def _words(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(text)]


def _decoded_variants(text: str) -> list[str]:
    """Сам ответ + попытки раскодировать base64-вставки и развернуть строку (частые способы вынести секрет)."""
    variants = [text, text[::-1]]
    for chunk in re.findall(r"[A-Za-z0-9+/=]{16,}", text):
        try:
            variants.append(base64.b64decode(chunk + "=" * (-len(chunk) % 4)).decode("utf-8", "ignore"))
        except Exception:
            pass
    return variants


def leaks_prompt(reply: str, protected_text: str, canary: str, min_ngram: int = 8) -> bool:
    """True, если ответ содержит секрет или длинный дословный кусок защищаемой части промпта.

    protected_text — только то, что клиенту видеть нельзя (секрет и правила), без публичных фактов и роли:
    иначе обычный ответ «ставка по ипотеке 12,5%» ложно считался бы утечкой.
    """
    sys_words = _words(protected_text)
    sys_ngrams = {tuple(sys_words[i:i + min_ngram]) for i in range(len(sys_words) - min_ngram + 1)}
    squeezed_canary = re.sub(r"\W", "", canary).lower()
    for variant in _decoded_variants(reply):
        if squeezed_canary in re.sub(r"\W", "", variant).lower():
            return True
        words = _words(variant)
        if any(tuple(words[i:i + min_ngram]) in sys_ngrams for i in range(len(words) - min_ngram + 1)):
            return True
    return False


def output_filter(reply: str, protected_text: str, canary: str) -> str:
    """Подменяет ответ шаблоном отказа, если в нём утечка. Не зависит от поведения модели."""
    return REFUSAL if leaks_prompt(reply, protected_text, canary) else reply
