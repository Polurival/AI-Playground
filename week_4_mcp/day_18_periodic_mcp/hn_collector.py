#!/usr/bin/env python3
"""
Автономный демон-сборщик данных HackerNews.

Запускается через MCP-инструмент start_scheduler как фоновый subprocess.
Периодически забирает топ-истории HN и сохраняет в SQLite.

Запуск вручную:
    python3 hn_collector.py [interval_minutes] [limit]
"""

import os
import signal
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
import schedule

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "hn_digest.db"
PID_FILE = DATA_DIR / "collector.pid"
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


def fetch_and_store(limit: int = 30) -> int:
    """Забирает топ-истории HN, сохраняет в SQLite. Возвращает кол-во сохранённых."""
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

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts}] Collected {fetched} stories", flush=True)
        return fetched

    except Exception as e:
        with _get_db() as conn:
            conn.execute(
                "INSERT INTO collection_log (stories_fetched, status) VALUES (?, ?)",
                (0, f"error: {e}"),
            )
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts}] Error: {e}", flush=True)
        return 0


def _cleanup(sig=None, frame=None) -> None:
    PID_FILE.unlink(missing_ok=True)
    sys.exit(0)


def main() -> None:
    interval = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 30

    _init_db()

    PID_FILE.write_text(str(os.getpid()))

    signal.signal(signal.SIGTERM, _cleanup)
    signal.signal(signal.SIGINT, _cleanup)

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] Collector started: interval={interval}m, limit={limit}", flush=True)

    fetch_and_store(limit)

    schedule.every(interval).minutes.do(fetch_and_store, limit=limit)

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
