"""Web access: search and page fetching. Pure stdlib, no API keys.

Search scrapes DuckDuckGo's HTML endpoint (falls back to the lite endpoint). Fetching strips a
page down to readable text. Both return plain strings; failures come back as "error: ..." so the
model can react instead of the run crashing.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.parse
import urllib.request
from html import unescape
from html.parser import HTMLParser

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
TIMEOUT = 15
MAX_FETCH_BYTES = 1_500_000
MAX_TEXT_CHARS = 8_000


def _get(url: str, data: bytes | None = None) -> tuple[str, str]:
    """GET (or POST when `data`) -> (final_url, decoded body)."""
    req = urllib.request.Request(url, data=data, headers={
        "User-Agent": USER_AGENT, "Accept-Language": "en,ru;q=0.8", "Accept": "text/html,*/*"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        raw = r.read(MAX_FETCH_BYTES)
        charset = r.headers.get_content_charset() or "utf-8"
        return r.geturl(), raw.decode(charset, errors="replace")


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", s))).strip()


def _unwrap_ddg(href: str) -> str:
    """DDG wraps result links as //duckduckgo.com/l/?uddg=<encoded-url>."""
    href = unescape(href)
    q = urllib.parse.urlparse(href).query
    uddg = urllib.parse.parse_qs(q).get("uddg")
    if uddg:
        return uddg[0]
    return "https:" + href if href.startswith("//") else href


def _parse_html_results(body: str) -> list[dict]:
    out = []
    for m in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', body, re.S):
        href, title = m.group(1), _clean(m.group(2))
        tail = body[m.end():m.end() + 3000]
        sn = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', tail, re.S)
        out.append({"title": title, "url": _unwrap_ddg(href), "snippet": _clean(sn.group(1)) if sn else ""})
    return out


def _parse_lite_results(body: str) -> list[dict]:
    out = []
    links = re.findall(r"<a[^>]+rel=\"nofollow\"[^>]+href=\"([^\"]+)\"[^>]*class='result-link'[^>]*>(.*?)</a>"
                       r"|<a[^>]+class='result-link'[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a>", body, re.S)
    snippets = [_clean(s) for s in re.findall(r"class='result-snippet'[^>]*>(.*?)</td>", body, re.S)]
    for i, l in enumerate(links):
        href, title = (l[0], l[1]) if l[0] else (l[2], l[3])
        out.append({"title": _clean(title), "url": _unwrap_ddg(href),
                    "snippet": snippets[i] if i < len(snippets) else ""})
    return out


def web_search(query: str, max_results: int = 5) -> str:
    """Search the web; returns numbered 'title / url / snippet' blocks."""
    if not query.strip():
        return "error: empty query"
    max_results = max(1, min(int(max_results), 10))
    q = urllib.parse.urlencode({"q": query})
    results: list[dict] = []
    last_err = ""
    for url, parser, post in (
        ("https://html.duckduckgo.com/html/", _parse_html_results, True),
        ("https://lite.duckduckgo.com/lite/", _parse_lite_results, True),
    ):
        try:
            _, body = _get(url, data=q.encode())
            results = parser(body)
            if results:
                break
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_err = str(exc)
    if not results:
        return f"error: search returned nothing ({last_err or 'blocked or no results'})"
    return "\n\n".join(
        f"{i}. {r['title']}\n   {r['url']}\n   {r['snippet']}" for i, r in enumerate(results[:max_results], 1))


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head", "nav", "footer", "form"}
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article", "pre"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title = ""
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)


def fetch_url(url: str, max_chars: int = MAX_TEXT_CHARS) -> str:
    """Download a page and return its readable text (title + body), truncated."""
    if not re.match(r"^https?://", url):
        return "error: url must start with http:// or https://"
    try:
        final, body = _get(url)
    except urllib.error.HTTPError as exc:
        return f"error: HTTP {exc.code} for {url}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return f"error: cannot fetch {url}: {exc}"
    if "<html" not in body[:2000].lower() and "<!doctype" not in body[:200].lower():
        text, title = body, ""                      # plain text / json / markdown
    else:
        p = _TextExtractor()
        p.feed(body)
        text = "".join(p.parts)
        title = " ".join(p.title.split())
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    max_chars = max(500, min(int(max_chars), 20_000))
    cut = len(text) > max_chars
    head = f"URL: {final}\n" + (f"Title: {title}\n" if title else "") + "\n"
    return head + text[:max_chars] + (f"\n\n[truncated: {len(text)} chars total]" if cut else "")
