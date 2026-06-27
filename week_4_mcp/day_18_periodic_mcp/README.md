# Day 18 — HackerNews Digest MCP (Periodic Tasks)

MCP-сервер с периодическим сбором топ-историй HackerNews, хранением в SQLite
и агентом на DeepSeek для работы с данными на естественном языке.

## Архитектура

```
agent_with_mcp.py          DeepSeek агент (function calling)
        │
        ▼
hn_mcp_client.py           MCP-клиент (stdio transport)
        │  запускает как subprocess
        ▼
hn_mcp_server.py           MCP-сервер (7 инструментов)
        │  читает/пишет SQLite      │  запускает как subprocess
        ▼                           ▼
  data/hn_digest.db         hn_collector.py
  (истории + лог)           (демон-планировщик)
```

**Ключевое решение:** MCP-сессия stateless — каждый вызов инструмента создаёт новый процесс сервера.
Поэтому планировщик живёт как отдельный subprocess (`hn_collector.py`), а MCP-сервер только
читает SQLite и управляет демоном через PID-файл.

## Файлы

| Файл | Роль |
|---|---|
| `hn_mcp_server.py` | MCP-сервер, 7 инструментов для сбора и анализа |
| `hn_collector.py` | Демон-планировщик, запускается через `start_scheduler` |
| `hn_mcp_client.py` | Клиент для прямого вызова MCP-инструментов |
| `agent_with_mcp.py` | Чат-агент DeepSeek с доступом к MCP |
| `data/hn_digest.db` | SQLite-база (создаётся при первом запуске) |
| `data/collector.pid` | PID демона (существует, пока планировщик запущен) |

## Установка

```bash
# venv уже есть в корне проекта (deepseek-env)
../../deepseek-env/bin/pip install schedule

# Или создать новый venv:
python3 -m venv .venv
.venv/bin/pip install mcp httpx schedule openai
```

## Запуск

### Вариант 1: Агент (рекомендуется)

```bash
source deepseek-env/bin/activate
export DEEPSEEK_API_KEY='your-key'
../../deepseek-env/bin/python3 agent_with_mcp.py
```

Примеры запросов агенту:
```
Собери свежие данные с HackerNews
Покажи дайджест за последние 12 часов
Запусти планировщик каждые 30 минут
Что пишут про Python на HN?
Статус планировщика
Останови планировщик
Удали данные старше 3 дней
```

### Вариант 2: Прямое тестирование клиента

```bash
../../deepseek-env/bin/python3 hn_mcp_client.py
```

Запускает `collect_now`, `get_scheduler_status`, `get_digest` и печатает результаты.

### Вариант 3: Демон напрямую

```bash
# interval_minutes=10, limit=30 историй
../../deepseek-env/bin/python3 hn_collector.py 10 30
```

## MCP-инструменты

| Инструмент | Параметры | Описание |
|---|---|---|
| `collect_now` | `limit=30` | Немедленный сбор топ-историй из HN API |
| `start_scheduler` | `interval_minutes=60`, `limit=30` | Запуск фонового демона-планировщика |
| `stop_scheduler` | — | Остановка демона (SIGTERM) |
| `get_scheduler_status` | — | Статус демона, последние 5 сборов, кол-во историй в базе |
| `get_digest` | `hours=24`, `min_score=0`, `keyword=""` | Дайджест топ-историй за период |
| `get_stories` | `limit=10`, `hours=24`, `keyword=""` | Сырые данные в JSON |
| `clear_old_data` | `older_than_days=7` | Удаление устаревших записей |

## Схема SQLite

```sql
-- Истории с HackerNews
CREATE TABLE stories (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    hn_id        INTEGER UNIQUE,      -- ID на HN (dedup через INSERT OR REPLACE)
    title        TEXT NOT NULL,
    url          TEXT,
    score        INTEGER DEFAULT 0,   -- рейтинг (upvotes)
    comments     INTEGER DEFAULT 0,   -- кол-во комментариев
    author       TEXT,
    hn_time      INTEGER,             -- unix timestamp поста на HN
    collected_at TEXT                 -- когда мы собрали (datetime)
);

-- Лог каждого сбора
CREATE TABLE collection_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    collected_at    TEXT,
    stories_fetched INTEGER DEFAULT 0,
    status          TEXT              -- "ok" или "error: <msg>"
);
```

## HackerNews API

Используется публичный Firebase REST API (без авторизации):

```
GET https://hacker-news.firebaseio.com/v0/topstories.json
    → список ID топ-500 историй

GET https://hacker-news.firebaseio.com/v0/item/{id}.json
    → детали истории (title, url, score, descendants, by, time)
```

## Как работает периодический сбор

1. Агент вызывает `start_scheduler(interval_minutes=60)`
2. MCP-сервер запускает `hn_collector.py 60 30` через `subprocess.Popen(..., start_new_session=True)`
3. Демон сохраняет свой PID в `data/collector.pid` и запускает первый сбор немедленно
4. Далее через библиотеку `schedule` — сбор каждые 60 минут
5. Агент в любой момент может вызвать `get_digest` — читает накопленные данные из SQLite
6. `stop_scheduler` посылает SIGTERM демону, PID-файл удаляется

```
t=0       t=60m     t=120m    t=180m
│collect  │collect  │collect  │collect  ...
└─────────┴─────────┴─────────┴──────────▶ время
          ↕         ↕
    агент запрашивает get_digest в любой момент
```
