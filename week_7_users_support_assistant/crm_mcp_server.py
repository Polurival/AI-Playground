#!/usr/bin/env python3
"""
Собственный MCP-сервер поверх JSON-«CRM» (пользователи и тикеты поддержки).

Это замена реальной CRM: данные лежат в crm_data/users.json и crm_data/tickets.json, а
ассистент поддержки не читает эти файлы напрямую — он ходит только через инструменты этого
сервера, как ходил бы в настоящую CRM по её API.

Построен по образцу week_4_mcp/day_17_create_mcp/git_mcp_server.py: FastMCP поднимает
stdio-сервер при запуске скрипта, клиент (crm_mcp_client.py) стартует его подпроцессом.

В отличие от git-сервера day_17, инструменты возвращают JSON, а не готовый текст: это API к
данным, а не к выводу команды. Раскладывать данные в текст для промпта — задача crm_context.py,
которому нужны ещё и отдельные поля (тариф, код ошибки) для перезаписи поискового запроса.

Каталог данных задаётся переменной окружения CRM_DATA_DIR (по умолчанию ./crm_data рядом с
этим файлом). Файлы перечитываются на каждом вызове, поэтому правки JSON видны сразу, без
перезапуска сервера.

Запуск (обычно не вручную, сервер общается по stdio с клиентом):
    python3 crm_mcp_server.py
"""

import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("crm-mcp-server")

DATA_DIR = Path(os.environ.get("CRM_DATA_DIR", Path(__file__).parent / "crm_data"))

# Поля тикета, отдаваемые в списках/поиске: шапка без переписки, чтобы ответ был компактным.
_TICKET_SUMMARY_FIELDS = ("ticket_id", "user_id", "subject", "status", "priority",
                          "product_area", "error_code", "created_at")


def _dump(payload) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _load(filename: str) -> list[dict]:
    """Читает JSON-массив из каталога данных CRM."""
    path = DATA_DIR / filename
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError(f"{path}: ожидался JSON-массив, получен {type(data).__name__}")
    return data


def _save(filename: str, rows: list[dict]) -> None:
    path = DATA_DIR / filename
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def _find(rows: list[dict], key: str, value: str) -> dict | None:
    value = (value or "").strip().upper()
    for row in rows:
        if str(row.get(key, "")).upper() == value:
            return row
    return None


def _summary(ticket: dict) -> dict:
    return {k: ticket.get(k, "") for k in _TICKET_SUMMARY_FIELDS}


@mcp.tool()
def crm_get_user(user_id: str) -> str:
    """Карточка пользователя из CRM (JSON): тариф, роль, включены ли SSO и 2FA, организация.

    Args:
        user_id: идентификатор пользователя, например 'USR-004'.
    """
    user = _find(_load("users.json"), "user_id", user_id)
    if not user:
        return _dump({"error": f"Пользователь '{user_id}' не найден в CRM."})
    return _dump(user)


@mcp.tool()
def crm_get_ticket(ticket_id: str) -> str:
    """Тикет поддержки целиком (JSON): тема, статус, раздел, код ошибки, переписка, заметки.

    Args:
        ticket_id: идентификатор тикета, например 'TCK-1042'.
    """
    ticket = _find(_load("tickets.json"), "ticket_id", ticket_id)
    if not ticket:
        return _dump({"error": f"Тикет '{ticket_id}' не найден в CRM."})
    return _dump(ticket)


@mcp.tool()
def crm_list_tickets(user_id: str = "", status: str = "", limit: int = 20) -> str:
    """Список тикетов (JSON, шапки без переписки) с необязательными фильтрами.

    Args:
        user_id: показать тикеты только этого пользователя (например 'USR-004'); пусто — все.
        status: фильтр по статусу: 'open', 'pending', 'closed'; пусто — любой.
        limit: максимум тикетов в ответе (по умолчанию 20).
    """
    tickets = _load("tickets.json")
    if user_id:
        tickets = [t for t in tickets if str(t.get("user_id", "")).upper() == user_id.strip().upper()]
    if status:
        tickets = [t for t in tickets if str(t.get("status", "")).lower() == status.strip().lower()]
    tickets = tickets[: max(1, limit)]
    return _dump([_summary(t) for t in tickets])


@mcp.tool()
def crm_search_tickets(query: str, limit: int = 10) -> str:
    """Поиск тикетов (JSON, шапки) по подстроке в теме, коде ошибки и тексте сообщений.

    Args:
        query: искомая подстрока, например 'SSO' или 'не могу войти'.
        limit: максимум тикетов в ответе (по умолчанию 10).
    """
    q = (query or "").strip().lower()
    if not q:
        return _dump({"error": "Пустой поисковый запрос."})
    found = []
    for t in _load("tickets.json"):
        haystack = " ".join([
            t.get("subject", ""),
            t.get("error_code", ""),
            t.get("product_area", ""),
            " ".join(m.get("text", "") for m in t.get("messages", [])),
        ]).lower()
        if q in haystack:
            found.append(t)
    return _dump([_summary(t) for t in found[: max(1, limit)]])


@mcp.tool()
def crm_add_ticket_note(ticket_id: str, note: str) -> str:
    """Добавляет внутреннюю заметку в тикет (единственный инструмент на запись).

    Args:
        ticket_id: идентификатор тикета, например 'TCK-1042'.
        note: текст заметки для команды поддержки.
    """
    note = (note or "").strip()
    if not note:
        return _dump({"error": "Пустая заметка не добавлена."})
    tickets = _load("tickets.json")
    ticket = _find(tickets, "ticket_id", ticket_id)
    if not ticket:
        return _dump({"error": f"Тикет '{ticket_id}' не найден в CRM."})
    ticket.setdefault("internal_notes", []).append(note)
    _save("tickets.json", tickets)
    return _dump({"ok": True, "ticket_id": ticket["ticket_id"],
                  "internal_notes_count": len(ticket["internal_notes"])})


if __name__ == "__main__":
    mcp.run(transport="stdio")
