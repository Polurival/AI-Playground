#!/usr/bin/env python3
"""
HackerNews Digest MCP-сервер.

Инструменты:
  collect_now          — немедленный сбор данных из HN
  start_scheduler      — запуск фонового демона-сборщика по расписанию
  stop_scheduler       — остановка демона
  get_scheduler_status — статус демона и статистика сборов
  get_digest           — дайджест топ-историй за период (фильтры: часы, рейтинг, ключевое слово)
  get_stories          — сырые данные историй в JSON
  clear_old_data       — удаление устаревших записей

Данные хранятся в data/hn_digest.db (SQLite).
Демон-планировщик — hn_collector.py, запускается как отдельный процесс.

Запуск (stdio-транспорт, используется клиентом):
    python3 hn_mcp_server.py
"""

import json
import os
import signal
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("hn-digest-mcp")

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "hn_digest.db"
PID_FILE = DATA_DIR / "collector.pid"
COLLECTOR_SCRIPT = str(Path(__file__).parent / "hn_collector.py")
HN_BASE = "https://hacker-news.firebaseio.com/v0"


def _get_db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS stories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hn_id INTEGER UNIQUE,
                title TEXT NOT NULL,
                url TEXT,
                score INTEGER DEFAULT 0,
                comments INTEGER DEFAULT 0,
                author TEXT,
                hn_time INTEGER,
                collected_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS collection_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                collected_at TEXT DEFAULT (datetime('now')),
                stories_fetched INTEGER DEFAULT 0,
                status TEXT
            );
        """)


_init_db()


def _is_collector_running() -> tuple[bool, int | None]:
    """Проверяет, жив ли демон-сборщик. Возвращает (running, pid)."""
    if not PID_FILE.exists():
        return False, None
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)
        return True, pid
    except (ValueError, ProcessLookupError, PermissionError):
        PID_FILE.unlink(missing_ok=True)
        return False, None


@mcp.tool()
def collect_now(limit: int = 30) -> str:
    """Немедленно собирает топ-истории HackerNews и сохраняет в базу.

    Args:
        limit: сколько топ-историй загрузить (по умолчанию 30, максимум 100).
    """
    limit = min(max(1, limit), 100)

    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(f"{HN_BASE}/topstories.json")
            resp.raise_for_status()
            ids = resp.json()[:limit]

            fetched = 0
            with _get_db() as conn:
                for story_id in ids:
                    try:
                        r = client.get(f"{HN_BASE}/item/{story_id}.json")
                        r.raise_for_status()
                        item = r.json()
                        if not item or item.get("type") != "story":
                            continue
                        conn.execute(
                            """
                            INSERT OR REPLACE INTO stories
                            (hn_id, title, url, score, comments, author, hn_time, collected_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                            """,
                            (
                                item["id"],
                                item.get("title", ""),
                                item.get("url", ""),
                                item.get("score", 0),
                                item.get("descendants", 0),
                                item.get("by", ""),
                                item.get("time", 0),
                            ),
                        )
                        fetched += 1
                    except Exception:
                        continue

                conn.execute(
                    "INSERT INTO collection_log (stories_fetched, status) VALUES (?, ?)",
                    (fetched, "ok"),
                )

        return f"Собрано и сохранено: {fetched} историй (top-{limit})."

    except Exception as e:
        return f"Ошибка сбора данных: {e}"


@mcp.tool()
def start_scheduler(interval_minutes: int = 60, limit: int = 30) -> str:
    """Запускает фоновый демон-планировщик для периодического сбора данных HN.

    Args:
        interval_minutes: интервал между сборами в минутах (минимум 5, по умолчанию 60).
        limit: сколько историй собирать за раз (по умолчанию 30, максимум 100).
    """
    running, pid = _is_collector_running()
    if running:
        return f"Планировщик уже запущен (PID {pid}). Вызовите stop_scheduler для остановки."

    interval_minutes = max(5, interval_minutes)
    limit = min(max(1, limit), 100)

    proc = subprocess.Popen(
        [sys.executable, COLLECTOR_SCRIPT, str(interval_minutes), str(limit)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    return (
        f"Планировщик запущен (PID {proc.pid}): "
        f"сбор каждые {interval_minutes} мин, top-{limit} историй."
    )


@mcp.tool()
def stop_scheduler() -> str:
    """Останавливает фоновый демон-планировщик."""
    running, pid = _is_collector_running()
    if not running:
        return "Планировщик не запущен."

    try:
        os.kill(pid, signal.SIGTERM)
        PID_FILE.unlink(missing_ok=True)
        return f"Планировщик остановлен (PID {pid})."
    except Exception as e:
        return f"Ошибка остановки (PID {pid}): {e}"


@mcp.tool()
def get_scheduler_status() -> str:
    """Возвращает статус демона-планировщика и статистику последних сборов."""
    running, pid = _is_collector_running()
    status_str = f"запущен (PID {pid})" if running else "остановлен"

    lines = [f"Планировщик: {status_str}"]

    with _get_db() as conn:
        last_log = conn.execute(
            "SELECT collected_at, stories_fetched, status FROM collection_log ORDER BY id DESC LIMIT 1"
        ).fetchone()

        if last_log:
            lines.append(
                f"Последний сбор: {last_log['collected_at']} "
                f"— {last_log['stories_fetched']} историй ({last_log['status']})"
            )
        else:
            lines.append("Последний сбор: данных нет")

        total = conn.execute("SELECT COUNT(*) as cnt FROM stories").fetchone()["cnt"]
        lines.append(f"Всего историй в базе: {total}")

        recent = conn.execute(
            "SELECT collected_at, stories_fetched, status FROM collection_log ORDER BY id DESC LIMIT 5"
        ).fetchall()

        if recent:
            lines.append("\nПоследние 5 сборов:")
            for r in recent:
                lines.append(f"  {r['collected_at']} → {r['stories_fetched']} историй ({r['status']})")

    return "\n".join(lines)


@mcp.tool()
def get_digest(hours: int = 24, min_score: int = 0, keyword: str = "") -> str:
    """Возвращает дайджест топ-историй HN за указанный период.

    Args:
        hours: период выборки в часах (по умолчанию 24).
        min_score: минимальный рейтинг историй (по умолчанию 0 — все).
        keyword: фильтр по ключевому слову в заголовке (необязательно).
    """
    since = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")

    with _get_db() as conn:
        query = """
            SELECT title, url, score, comments, author, collected_at
            FROM stories
            WHERE collected_at >= ? AND score >= ?
        """
        params: list = [since, min_score]

        if keyword:
            query += " AND LOWER(title) LIKE ?"
            params.append(f"%{keyword.lower()}%")

        query += " ORDER BY score DESC LIMIT 20"
        rows = conn.execute(query, params).fetchall()

    if not rows:
        msg = f"Нет историй за {hours}ч"
        if min_score:
            msg += f" с рейтингом ≥{min_score}"
        if keyword:
            msg += f" по теме '{keyword}'"
        return msg + ". Запустите collect_now или start_scheduler для сбора данных."

    header = f"Дайджест HackerNews за {hours}ч | {len(rows)} историй"
    if min_score:
        header += f" | min_score={min_score}"
    if keyword:
        header += f" | тема='{keyword}'"

    lines = [header, ""]
    for i, row in enumerate(rows, 1):
        url_part = f"\n   {row['url'][:80]}" if row["url"] else ""
        lines.append(f"{i}. ⬆{row['score']} 💬{row['comments']}  {row['title']}{url_part}")

    return "\n".join(lines)


@mcp.tool()
def get_stories(limit: int = 10, hours: int = 24, keyword: str = "") -> str:
    """Возвращает сырые данные историй из базы в формате JSON.

    Args:
        limit: максимум историй (по умолчанию 10).
        hours: период выборки в часах (по умолчанию 24).
        keyword: фильтр по ключевому слову в заголовке.
    """
    since = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")

    with _get_db() as conn:
        query = """
            SELECT hn_id, title, url, score, comments, author, collected_at
            FROM stories
            WHERE collected_at >= ?
        """
        params: list = [since]

        if keyword:
            query += " AND LOWER(title) LIKE ?"
            params.append(f"%{keyword.lower()}%")

        query += f" ORDER BY score DESC LIMIT {limit}"
        rows = conn.execute(query, params).fetchall()

    if not rows:
        return json.dumps([], ensure_ascii=False)

    result = [
        {
            "hn_id": r["hn_id"],
            "title": r["title"],
            "url": r["url"],
            "score": r["score"],
            "comments": r["comments"],
            "author": r["author"],
            "collected_at": r["collected_at"],
            "hn_url": f"https://news.ycombinator.com/item?id={r['hn_id']}",
        }
        for r in rows
    ]
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def clear_old_data(older_than_days: int = 7) -> str:
    """Удаляет истории и логи старше указанного числа дней.

    Args:
        older_than_days: возраст данных для удаления (по умолчанию 7 дней).
    """
    cutoff = (datetime.now() - timedelta(days=older_than_days)).strftime("%Y-%m-%d %H:%M:%S")

    with _get_db() as conn:
        deleted_s = conn.execute(
            "DELETE FROM stories WHERE collected_at < ?", (cutoff,)
        ).rowcount
        deleted_l = conn.execute(
            "DELETE FROM collection_log WHERE collected_at < ?", (cutoff,)
        ).rowcount

    return f"Удалено: {deleted_s} историй и {deleted_l} лог-записей старше {older_than_days} дн."


if __name__ == "__main__":
    mcp.run(transport="stdio")
