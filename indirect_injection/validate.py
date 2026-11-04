"""Слой 3: output validation. Проверяет ответ агента ДЕТЕРМИНИРОВАННО, независимо от того, что «решила» модель.

Идея: ответ не должен содержать ничего, чего нет в видимых данных (ссылки, домены, суммы), не должен выходить
из заданного формата и не должен нести каналы утечки (markdown-картинки на внешние URL). Что нельзя проверить
кодом (смысловая подмена без ссылок и цифр), этот слой не поймает — см. README.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

_TLD = r"(?:com|ru|org|net|io|info|dev|app|xyz|top|example|me|co|cc|biz|online|site|su|рф)"
_URL = re.compile(r"https?://[^\s)\]>\"'`]+", re.I)
_DOMAIN = re.compile(rf"\b(?:[a-z0-9-]+\.)+{_TLD}\b", re.I)
_MD_IMG = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MONEY = re.compile(r"(\d[\d\s.,]*)\s?(\$|₽|руб\w*|usd|долл\w*|€|eur)|(\$|€)\s?(\d[\d\s.,]*)", re.I)


@dataclass
class Verdict:
    ok: bool
    final: str
    problems: list[str] = field(default_factory=list)


def domains(text: str) -> set[str]:
    out = {urlparse(u).netloc.lower().removeprefix("www.") for u in _URL.findall(text)}
    out |= {d.lower().removeprefix("www.") for d in _DOMAIN.findall(text)}
    return {d for d in out if d}


def _amounts(text: str) -> set[str]:
    res = set()
    for m in _MONEY.finditer(text):
        num = m.group(1) or m.group(4)
        num = re.sub(r"[\s]", "", num).replace(",", ".").rstrip(".")
        try:
            res.add(str(float(num)).removesuffix(".0"))
        except ValueError:
            pass
    return res


def _known_domain(d: str, allowed: set[str]) -> bool:
    return any(d == a or d.endswith("." + a) for a in allowed)


def validate_summary(reply: str, visible: str, hrefs: list[str]) -> Verdict:
    """Summary письма: ни одной ссылки/домена, которых нет в видимом письме; никаких внешних картинок."""
    allowed = domains(visible) | {urlparse(h).netloc.lower().removeprefix("www.") for h in hrefs}
    problems, kept = [], []
    for line in reply.splitlines():
        bad = [d for d in domains(line) if not _known_domain(d, allowed)]
        if _MD_IMG.search(line):
            problems.append("markdown-картинка во внешний URL (канал утечки)")
            continue
        if bad:
            problems.append(f"домен/ссылка, которой нет в письме: {', '.join(sorted(bad))}")
            continue
        kept.append(line)
    final = "\n".join(kept).strip()
    if problems:
        final += "\n\n⚠ Из summary удалены строки со ссылками, которых нет в письме."
    return Verdict(not problems, final, problems)


_BLOCKED = {"error": "output validation failed"}


def parse_json_reply(reply: str) -> dict | None:
    m = re.search(r"\{.*\}", reply, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def validate_analysis(reply: str, canaries: list[str]) -> Verdict:
    """Ответ аналитика: ровно {risk_level: low|medium|high, summary: str<=500}, без URL и секретов, без текста вокруг JSON."""
    problems = []
    data = parse_json_reply(reply)
    stripped = re.sub(r"^```(?:json)?|```$", "", reply.strip(), flags=re.M).strip()
    if data is None:
        problems.append("ответ — не JSON")
    else:
        if set(data) != {"risk_level", "summary"}:
            problems.append(f"поля не по схеме: {sorted(data)}")
        if data.get("risk_level") not in ("low", "medium", "high"):
            problems.append(f"risk_level вне enum: {data.get('risk_level')!r}")
        if not isinstance(data.get("summary"), str) or len(data.get("summary", "")) > 500:
            problems.append("summary не строка ≤500 символов")
        if not stripped.startswith("{") or not stripped.endswith("}"):
            problems.append("текст вне JSON-объекта")
    flat = reply.lower()
    if any(c.lower() in flat for c in canaries):
        problems.append("в ответе секрет/служебный маркер")
    if _URL.search(reply) or _MD_IMG.search(reply):
        problems.append("URL в ответе аналитика")
    return Verdict(not problems, reply if not problems else json.dumps(_BLOCKED), problems)


def validate_answer(reply: str, visible_pages: list[str], hrefs: list[str]) -> Verdict:
    """Ответ поискового агента: домены и суммы должны встречаться в ВИДИМОМ тексте найденных страниц."""
    corpus = "\n".join(visible_pages)
    allowed = domains(corpus) | {urlparse(h).netloc.lower().removeprefix("www.") for h in hrefs}
    problems = []
    for d in domains(reply):
        if not _known_domain(d, allowed):
            problems.append(f"домен, которого нет в найденных страницах: {d}")
    unknown = _amounts(reply) - _amounts(corpus)
    if unknown:
        problems.append(f"сумма не подтверждена текстом страниц: {', '.join(sorted(unknown))}")
    if _MD_IMG.search(reply):
        problems.append("markdown-картинка во внешний URL")
    final = reply if not problems else "Не удалось надёжно ответить: найденные страницы содержат непроверяемые данные (" + "; ".join(problems) + ")."
    return Verdict(not problems, final, problems)


_NET = re.compile(r"\b(requests|urllib|http\.client|httpx|aiohttp|socket|smtplib|ftplib|subprocess|os\.system|eval|exec)\b")
_ENV = re.compile(r"os\.environ|os\.getenv|getpass|\.ssh|\.aws|/etc/passwd")


def validate_code(reply: str, context_files: str, task_allows_network: bool = False) -> Verdict:
    """Сгенерированный код: без сети/процессов/чтения окружения, если задача этого не просила; без URL не из репозитория."""
    problems = []
    if not task_allows_network:
        if _NET.search(reply):
            problems.append("сетевой/процессный вызов, которого не просили")
        if _ENV.search(reply):
            problems.append("доступ к окружению/секретам")
    for d in domains(reply):
        if not _known_domain(d, domains(context_files)):
            problems.append(f"URL/домен, которого нет в репозитории: {d}")
    final = reply if not problems else "# Код отклонён валидатором: " + "; ".join(problems)
    return Verdict(not problems, final, problems)
