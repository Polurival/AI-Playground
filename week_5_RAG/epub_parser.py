"""EPUB parser: extracts (filename, chapter_title, clean_text) per XHTML file."""

import re
import zipfile
import warnings
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


EPUB_PATH = "Alice's_Adventures_in_Wonderland_by_Lewis_Carroll.3.epub"
SOURCE_NAME = "Alice's_Adventures_in_Wonderland_by_Lewis_Carroll.3.epub"


def _extract_title(soup: BeautifulSoup, filename: str) -> str:
    for tag in ("h1", "h2", "h3"):
        el = soup.find(tag)
        if el and el.get_text(strip=True):
            return el.get_text(" ", strip=True)
    title_el = soup.find("title")
    if title_el:
        return title_el.get_text(strip=True)
    return filename


def _clean_text(soup: BeautifulSoup) -> str:
    for el in soup(["script", "style", "nav", "header", "footer"]):
        el.decompose()
    text = soup.get_text(separator="\n")
    lines = [ln.strip() for ln in text.splitlines()]
    paragraphs = []
    blank = 0
    for ln in lines:
        if ln:
            paragraphs.append(ln)
            blank = 0
        else:
            blank += 1
            if blank == 1:
                paragraphs.append("")
    return "\n".join(paragraphs).strip()


def parse_epub(epub_path: str = EPUB_PATH) -> list[dict]:
    """Return list of dicts with keys: filename, title, text."""
    chapters = []
    with zipfile.ZipFile(epub_path) as zf:
        def _sort_key(name: str) -> int:
            m = re.search(r"-(\d+)\.htm\.xhtml$", name)
            return int(m.group(1)) if m else -1

        xhtml_files = sorted(
            (f for f in zf.namelist()
             if f.endswith(".xhtml") and "OEBPS/" in f and "toc" not in f and "wrap" not in f),
            key=_sort_key,
        )
        for fname in xhtml_files:
            raw = zf.read(fname).decode("utf-8", errors="replace")
            soup = BeautifulSoup(raw, "lxml")
            text = _clean_text(soup)
            if len(text) < 50:
                continue
            title = _extract_title(soup, fname.split("/")[-1])
            chapters.append({
                "filename": fname.split("/")[-1],
                "title": title,
                "text": text,
            })
    return chapters
