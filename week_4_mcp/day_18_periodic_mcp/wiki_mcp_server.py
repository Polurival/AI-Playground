#!/usr/bin/env python3
"""
Wikipedia MCP-сервер.

Инструменты:
  search_wikipedia    — поиск статей по запросу, возвращает JSON-список с titles/snippets/urls
  get_article_summary — вводный абзац + описание статьи по точному заголовку

Запуск (stdio-транспорт):
    python3 wiki_mcp_server.py
"""

import json
import urllib.parse

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("wikipedia-mcp")

WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKI_REST = "https://en.wikipedia.org/api/rest_v1/page/summary"
HEADERS = {"User-Agent": "HN-Research-MCP/1.0 (educational project; contact: user@example.com)"}


def _strip_html(text: str) -> str:
    """Убирает простые HTML-теги из сниппета поиска."""
    import re
    return re.sub(r"<[^>]+>", "", text)


@mcp.tool()
def search_wikipedia(query: str, limit: int = 5) -> str:
    """Ищет статьи в Wikipedia по запросу. Возвращает JSON-список результатов.

    Args:
        query: поисковый запрос (лучше на английском).
        limit: максимум результатов (1–10, по умолчанию 5).
    """
    limit = min(max(1, limit), 10)
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": limit,
        "srprop": "snippet",
        "format": "json",
        "utf8": 1,
    }
    try:
        with httpx.Client(timeout=10, headers=HEADERS) as client:
            resp = client.get(WIKI_API, params=params)
            resp.raise_for_status()
            data = resp.json()

        results = [
            {
                "title": item["title"],
                "snippet": _strip_html(item.get("snippet", "")),
                "url": (
                    "https://en.wikipedia.org/wiki/"
                    + urllib.parse.quote(item["title"].replace(" ", "_"))
                ),
            }
            for item in data.get("query", {}).get("search", [])
        ]
        return json.dumps(results, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
def get_article_summary(title: str) -> str:
    """Возвращает вводный абзац и описание статьи Wikipedia.

    Args:
        title: точный заголовок статьи (например "Large language model" или "Rust (programming language)").
    """
    encoded = urllib.parse.quote(title.replace(" ", "_"))
    url = f"{WIKI_REST}/{encoded}"
    try:
        with httpx.Client(timeout=10, headers={**HEADERS, "Accept": "application/json"}) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.json()

        result = {
            "title": data.get("title", title),
            "description": data.get("description", ""),
            "extract": data.get("extract", ""),
            "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run(transport="stdio")
