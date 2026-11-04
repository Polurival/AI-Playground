"""Слой 1: input sanitization. Оставляет только то, что человек увидел бы глазами.

Что режем:
  * невидимый Unicode: zero-width, bidi-управляющие, блок Unicode Tags U+E0000–E007F (ASCII-«контрабанда»);
  * HTML: комментарии, script/style/head/template, скрытые элементы (display:none, белый текст, нулевой шрифт...),
    все атрибуты (title/alt/data-*/meta не попадают в текст);
  * markdown: title у ссылки `[текст](url "title")` и картинки `![alt](url)`.

level=1 — «очевидные» приёмы (инлайновые стили). level=2 — после того как адаптивные атаки
обошли level=1: классы из <style>, почти белый цвет, вынос за экран, noscript, закрытый <details> и т. п.
Это эвристики-чёрный список: надёжнее рендерить страницу в браузере и брать innerText видимых узлов (см. README).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from html.parser import HTMLParser

_ZERO_WIDTH = {0x200B, 0x200C, 0x200D, 0x2060, 0x2061, 0x2062, 0x2063, 0x2064, 0xFEFF, 0x00AD, 0x180E, 0x034F}
_BIDI = set(range(0x202A, 0x202F)) | set(range(0x2066, 0x206A)) | {0x200E, 0x200F, 0x061C}
_TAGS = range(0xE0000, 0xE0080)
_VARIATION = set(range(0xFE00, 0xFE10)) | set(range(0xE0100, 0xE01F0))


def strip_invisible(text: str) -> tuple[str, list[str]]:
    """Убирает невидимые символы; возвращает чистый текст и находки (декодированный Tags-текст показываем)."""
    found: list[str] = []
    tag_chars = [chr(ord(c) - 0xE0000) for c in text if ord(c) in _TAGS and 0x20 <= ord(c) - 0xE0000 < 0x7F]
    if any(ord(c) in _TAGS for c in text):
        found.append(f"unicode-tags: скрытый ASCII-текст {''.join(tag_chars)!r}")
    n_zw = sum(1 for c in text if ord(c) in _ZERO_WIDTH or ord(c) in _VARIATION)
    if n_zw:
        found.append(f"zero-width: {n_zw} симв.")
    if any(ord(c) in _BIDI for c in text):
        found.append("bidi-управляющие символы")
    drop = _ZERO_WIDTH | _BIDI | _VARIATION
    clean = "".join(c for c in text if ord(c) not in drop and ord(c) not in _TAGS)
    return unicodedata.normalize("NFC", clean), found


# ---------------------------------------------------------------- HTML
_VOID = {"br", "hr", "img", "meta", "link", "input", "area", "base", "col", "embed", "source", "track", "wbr"}
_BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table", "ul", "ol", "section", "blockquote", "pre", "article"}
_ALWAYS_SKIP_1 = {"script", "style", "head", "template", "title"}
_ALWAYS_SKIP_2 = _ALWAYS_SKIP_1 | {"noscript", "textarea", "iframe", "object", "svg", "select", "datalist", "canvas"}
_WHITE = {"white", "#fff", "#ffffff", "rgb(255,255,255)", "rgb(255, 255, 255)"}


def _parse_style(s: str) -> dict[str, str]:
    out = {}
    for part in s.split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip().lower()] = re.sub(r"\s*!important", "", v.strip().lower())
    return out


def _px(v: str) -> float | None:
    m = re.fullmatch(r"(-?[\d.]+)\s*(px|pt|em|rem|%)?", v.strip())
    return float(m.group(1)) if m else None


def _rgb(v: str) -> tuple[int, int, int] | None:
    v = v.strip().lower()
    if v in ("white",):
        return 255, 255, 255
    m = re.fullmatch(r"#([0-9a-f]{3})", v)
    if m:
        return tuple(int(c * 2, 16) for c in m.group(1))  # type: ignore[return-value]
    m = re.fullmatch(r"#([0-9a-f]{6})", v)
    if m:
        h = m.group(1)
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    m = re.fullmatch(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", v)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    return None


def _style_hidden(st: dict[str, str], level: int) -> bool:
    if st.get("display") == "none" or st.get("visibility") in ("hidden", "collapse") or st.get("opacity") in ("0", "0.0"):
        return True
    fs = _px(st.get("font-size", ""))
    if fs is not None and fs <= 2:
        return True
    col = st.get("color", "")
    if level == 1:
        return col.replace(" ", "") in {c.replace(" ", "") for c in _WHITE}
    # level 2: порог по яркости вместо точного «белого»
    rgb = _rgb(col)
    if rgb and min(rgb) >= 0xE8:
        return True
    pos_left, pos_top = _px(st.get("left", "")), _px(st.get("top", ""))
    if st.get("position") in ("absolute", "fixed") and ((pos_left is not None and pos_left <= -200) or (pos_top is not None and pos_top <= -200)):
        return True
    ti = _px(st.get("text-indent", ""))
    if ti is not None and ti <= -200:
        return True
    for dim in ("height", "width", "max-height", "max-width"):
        v = _px(st.get(dim, ""))
        if v is not None and v == 0 and st.get("overflow", "") in ("hidden", "clip"):
            return True
    if "clip" in st and "rect(0" in st["clip"].replace(" ", ""):
        return True
    if "clip-path" in st and "inset(100%" in st["clip-path"].replace(" ", ""):
        return True
    return False


def _css_rules(css: str) -> list[tuple[str, dict[str, str]]]:
    """Очень простой разбор: селекторы `.cls`, `#id`, `tag` (без комбинаторов) -> свойства."""
    rules = []
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", re.sub(r"/\*.*?\*/", "", css, flags=re.S)):
        for s in sel.split(","):
            s = s.strip()
            if re.fullmatch(r"[.#]?[\w-]+", s):
                rules.append((s, _parse_style(body)))
    return rules


@dataclass
class _Visible(HTMLParser):
    level: int = 2
    rules: list = field(default_factory=list)
    chunks: list = field(default_factory=list)
    links: list = field(default_factory=list)
    findings: list = field(default_factory=list)
    stack: list = field(default_factory=list)  # (tag, hidden)
    hidden_chars: int = 0

    def __post_init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)

    def _is_hidden(self, tag: str, attrs: dict[str, str | None]) -> bool:
        skip = _ALWAYS_SKIP_2 if self.level >= 2 else _ALWAYS_SKIP_1
        if tag in skip or "hidden" in attrs:
            return True
        if self.level >= 2:
            if (attrs.get("aria-hidden") or "").lower() == "true":
                return True
            if tag == "input" and (attrs.get("type") or "").lower() == "hidden":
                return True
        st = _parse_style(attrs.get("style") or "")
        if self.level >= 2:  # правила из <style> (по тегу, id, классам); инлайн сильнее
            classes = (attrs.get("class") or "").split()
            merged: dict[str, str] = {}
            for sel, props in self.rules:
                if sel == tag or (sel.startswith(".") and sel[1:] in classes) or (sel.startswith("#") and sel[1:] == attrs.get("id")):
                    merged.update(props)
            merged.update(st)
            st = merged
        return _style_hidden(st, self.level)

    def handle_starttag(self, tag, attrs_list):
        attrs = dict(attrs_list)
        parent_hidden = bool(self.stack and self.stack[-1][1])
        hidden = parent_hidden or self._is_hidden(tag, attrs)
        if self.level >= 2 and tag == "details" and "open" not in attrs:
            self.stack.append(("details_closed", parent_hidden))  # содержимое закрытого <details>, кроме <summary>, скрыто
            return
        if self.level >= 2 and self.stack and self.stack[-1][0] == "details_closed" and tag != "summary" and not parent_hidden:
            hidden = True
        if tag == "a" and attrs.get("href") and not hidden:
            self.links.append(attrs["href"])
        if tag in _BLOCK and not hidden:
            self.chunks.append("\n")
        if tag not in _VOID:
            self.stack.append((tag, hidden))

    def handle_startendtag(self, tag, attrs):
        if tag in _BLOCK:
            self.chunks.append("\n")

    def handle_endtag(self, tag):
        tag = "details_closed" if tag == "details" and any(t == "details_closed" for t, _ in self.stack) else tag
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break
        if tag in _BLOCK:
            self.chunks.append("\n")

    def handle_data(self, data):
        if self.stack and self.stack[-1][1]:
            self.hidden_chars += len(data.strip())
            return
        if self.stack and self.stack[-1][0] == "details_closed" and data.strip():
            self.hidden_chars += len(data.strip())
            return
        self.chunks.append(data)

    def handle_comment(self, data):
        self.findings.append(f"HTML-комментарий удалён: {data.strip()[:60]!r}")


_HTML_RE = re.compile(r"<!--|</?[a-zA-Z][a-zA-Z0-9-]*(?:\s[^<>]*)?/?>")
_MD_IMG = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK = re.compile(r"\[([^\]]*)\]\(\s*([^)\s]*)(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)")


def clean_markdown(text: str) -> tuple[str, list[str]]:
    found = []
    if _MD_IMG.search(text):
        found.append("markdown-картинка удалена (канал утечки данных)")
    text = _MD_IMG.sub("", text)
    for m in _MD_LINK.finditer(text):
        if re.search(r'\s+["\']', m.group(0)):
            found.append("title у markdown-ссылки удалён")
    text = _MD_LINK.sub(r"\1", text)
    return text, found


@dataclass
class Sanitized:
    text: str
    links: list[str]
    findings: list[str]


def sanitize(content: str, level: int = 2) -> Sanitized:
    """Видимый текст + найденные приёмы сокрытия. Порядок: невидимый Unicode -> HTML -> markdown -> пробелы."""
    text, findings = strip_invisible(content)
    links: list[str] = []
    if _HTML_RE.search(text):
        p = _Visible(level=level)
        if level >= 2:
            for css in re.findall(r"<style[^>]*>(.*?)</style>", text, flags=re.S | re.I):
                p.rules += _css_rules(css)
        p.feed(text)
        p.close()
        text = "".join(p.chunks)
        links = p.links
        findings += p.findings
        if p.hidden_chars:
            findings.append(f"скрытый HTML-текст удалён ({p.hidden_chars} симв.)")
    else:
        text = re.sub(r"<!--(.*?)-->", lambda m: (findings.append(f"HTML-комментарий удалён: {m.group(1).strip()[:60]!r}") or ""), text, flags=re.S)
    text, md = clean_markdown(text)
    findings += md
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return Sanitized(text, links, findings)


# ---------------------------------------------------------------- эвристический детектор (только сигнал, не блокировка)
_SUSPECT = re.compile(
    r"(ignore (all |any )?(previous|prior|above)|disregard|system override|new instructions?|"
    r"ai (assistant|agent|model)s?\b|assistant[s]?[: ,]|"
    r"игнорируй|проигнорируй|забудь (все|предыдущие)|для (ии|ai|нейро|автоматическ|ассистент)|"
    r"ии-ассистент|ассистент(у|ам|а)?[,:]|не (упоминай|сообщай|говори) (пользовател|что)|системн\w+ (промпт|инструкц))",
    re.I,
)


def suspicious(text: str) -> list[str]:
    """Ключевые слова — слабый сигнал: обходится перефразом и другим языком. Используем только как предупреждение."""
    return sorted({m.group(0).lower() for m in _SUSPECT.finditer(text)})
