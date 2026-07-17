"""Контекст пользователя/тикета из CRM — через MCP.

Единственная дверь ассистента в CRM. Здесь MCP-вызовы (crm_mcp_client -> crm_mcp_server поверх
JSON) превращаются в две вещи:

- `text`  — компактный русский блок для промпта генерации («что мы знаем о клиенте и его тикете»);
- `facts` — отдельные поля (тариф, код ошибки, раздел продукта), которые подмешиваются в
  перезапись поискового запроса: именно из-за них «почему не работает авторизация» с тикетом
  TCK-1042 ищется как «SSO-402 SAML тариф Free», а не как общий вопрос про вход.

Ассистент никогда не читает crm_data/*.json напрямую — только эти функции.
"""

import asyncio
import json
import logging

from crm_mcp_client import call_crm_tool

logger = logging.getLogger(__name__)

_PLAN_LABELS = {"free": "Free", "pro": "Pro", "business": "Business"}


def _text_of(result) -> str:
    """Склеивает content-элементы результата MCP-вызова в одну строку."""
    parts = [getattr(item, "text", str(item)) for item in getattr(result, "content", [])]
    return "\n".join(p for p in parts if p).strip()


async def _call_json(tool: str, args: dict, crm_dir: str = ""):
    """Вызывает инструмент CRM MCP и разбирает его JSON-ответ. None при любой ошибке."""
    try:
        raw = _text_of(await call_crm_tool(tool, args, crm_dir))
        data = json.loads(raw)
    except Exception as exc:
        logger.warning("[CRM-MCP] %s%s failed: %s", tool, args, exc)
        return None
    if isinstance(data, dict) and "error" in data:
        logger.info("[CRM-MCP] %s: %s", tool, data["error"])
        return None
    return data


def call_json(tool: str, args: dict, crm_dir: str = ""):
    """Синхронная обёртка над одним MCP-вызовом."""
    return asyncio.run(_call_json(tool, args, crm_dir))


def _format_user(user: dict) -> str:
    plan = _PLAN_LABELS.get(str(user.get("plan", "")).lower(), user.get("plan", "—"))
    return "\n".join([
        f"Пользователь: {user.get('name', '—')} <{user.get('email', '—')}> ({user['user_id']})",
        f"Организация: {user.get('org', '—')} | Роль: {user.get('role', '—')}",
        f"Тариф: {plan}",
        f"SSO включён: {'да' if user.get('sso_enabled') else 'нет'} | "
        f"2FA включена: {'да' if user.get('mfa_enabled') else 'нет'}",
        f"Участников в рабочем пространстве: {user.get('seats_used', '—')} | "
        f"клиент с {user.get('created_at', '—')}",
    ])


def _format_ticket(ticket: dict) -> str:
    lines = [
        f"Тикет {ticket['ticket_id']}: {ticket.get('subject', '')}",
        f"Статус: {ticket.get('status', '—')} | Приоритет: {ticket.get('priority', '—')} | "
        f"Раздел: {ticket.get('product_area', '—')}",
        f"Код ошибки: {ticket.get('error_code') or '(не указан)'} | "
        f"Версия клиента: {ticket.get('app_version', '—')} | Создан: {ticket.get('created_at', '—')}",
    ]
    if ticket.get("messages"):
        lines.append("Переписка по тикету:")
        for msg in ticket["messages"]:
            lines.append(f"  [{msg.get('at', '')}] {msg.get('author', '?')}: {msg.get('text', '')}")
    if ticket.get("internal_notes"):
        lines.append("Внутренние заметки поддержки:")
        for note in ticket["internal_notes"]:
            lines.append(f"  - {note}")
    return "\n".join(lines)


def _facts(user: dict | None, ticket: dict | None) -> dict:
    """Поля, влияющие на поиск и на ответ."""
    facts: dict = {}
    if user:
        facts.update({
            "user_id": user.get("user_id", ""),
            "plan": str(user.get("plan", "")).lower(),
            "role": user.get("role", ""),
            "sso_enabled": bool(user.get("sso_enabled")),
            "mfa_enabled": bool(user.get("mfa_enabled")),
        })
    if ticket:
        facts.update({
            "ticket_id": ticket.get("ticket_id", ""),
            "subject": ticket.get("subject", ""),
            "product_area": ticket.get("product_area", ""),
            "error_code": ticket.get("error_code", ""),
            "status": ticket.get("status", ""),
        })
    return facts


def _empty(reason: str) -> dict:
    return {"text": "", "facts": {}, "found": False, "reason": reason}


def user_context(user_id: str, crm_dir: str = "", include_tickets: bool = True) -> dict:
    """Контекст по пользователю: карточка + его открытые тикеты."""
    user = call_json("crm_get_user", {"user_id": user_id}, crm_dir)
    if not user:
        return _empty(f"Пользователь '{user_id}' не найден в CRM.")
    blocks = [_format_user(user)]
    if include_tickets:
        open_tickets = call_json(
            "crm_list_tickets", {"user_id": user_id, "status": "open", "limit": 5}, crm_dir
        ) or []
        if open_tickets:
            lines = [f"  - {t['ticket_id']} [{t.get('error_code') or '—'}] {t.get('subject', '')}"
                     for t in open_tickets]
            blocks.append("Открытые тикеты пользователя:\n" + "\n".join(lines))
    return {"text": "\n\n".join(blocks), "facts": _facts(user, None), "found": True, "reason": ""}


def ticket_context(ticket_id: str, crm_dir: str = "") -> dict:
    """Контекст по тикету: сам тикет + карточка его автора (тариф решает исход половины вопросов)."""
    ticket = call_json("crm_get_ticket", {"ticket_id": ticket_id}, crm_dir)
    if not ticket:
        return _empty(f"Тикет '{ticket_id}' не найден в CRM.")
    user = call_json("crm_get_user", {"user_id": ticket.get("user_id", "")}, crm_dir)
    blocks = []
    if user:
        blocks.append(_format_user(user))
    blocks.append(_format_ticket(ticket))
    return {"text": "\n\n".join(blocks), "facts": _facts(user, ticket), "found": True, "reason": ""}


def list_tickets(user_id: str = "", status: str = "", limit: int = 20, crm_dir: str = "") -> list[dict]:
    """Шапки тикетов с фильтрами (для команды /tickets)."""
    return call_json(
        "crm_list_tickets", {"user_id": user_id, "status": status, "limit": limit}, crm_dir
    ) or []


def search_tickets(query: str, limit: int = 10, crm_dir: str = "") -> list[dict]:
    return call_json("crm_search_tickets", {"query": query, "limit": limit}, crm_dir) or []


def add_note(ticket_id: str, note: str, crm_dir: str = "") -> str:
    """Записать внутреннюю заметку в тикет (единственная запись в CRM)."""
    res = call_json("crm_add_ticket_note", {"ticket_id": ticket_id, "note": note}, crm_dir)
    if not res:
        return f"не удалось добавить заметку в '{ticket_id}'"
    return f"заметка добавлена в {res['ticket_id']} (всего: {res['internal_notes_count']})"


def facts_for_query(facts: dict) -> str:
    """Короткая строка фактов, подмешиваемая в перезапись поискового запроса."""
    bits = []
    if facts.get("error_code"):
        bits.append(f"код ошибки {facts['error_code']}")
    if facts.get("product_area"):
        bits.append(f"раздел {facts['product_area']}")
    if facts.get("subject"):
        bits.append(f"тема обращения: {facts['subject']}")
    if facts.get("plan"):
        bits.append(f"тариф клиента {_PLAN_LABELS.get(facts['plan'], facts['plan'])}")
    return "; ".join(bits)
