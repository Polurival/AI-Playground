#!/usr/bin/env python3
"""Демонстрация ассистента поддержки пользователей: шесть разделов, каждый показывает свой аспект.

Скрипт дёргает Python-API напрямую (а не CLI через подпроцесс), чтобы показать внутренности —
переписанный поисковый запрос, косинус и rerank, факты из CRM. Это не тест: он ничего не
утверждает, а печатает результат под понятными заголовками, чтобы за один прогон было видно,
что и почему делает ассистент.

Что показывают разделы:
  A. CRM через MCP без единого вызова LLM (список тикетов, карточка клиента + тикета).
  B. Ядро задания: один вопрос × три тикета -> три разных верных ответа.
  C. Контекст тикета управляет и ПОИСКОМ: тот же вопрос с тикетом и без — разные запросы/источники.
  D. Тариф решает и в других разделах (API-429 на Pro).
  E. Вопрос вне документации -> отказ по порогу rerank, LLM не вызывается.
  F. Запись в CRM через MCP: заметка в тикет (с откатом, чтобы не пачкать данные).

Запуск:
    ../deepseek-env/bin/python demo.py            # все разделы
    ../deepseek-env/bin/python demo.py A C E       # только выбранные разделы

Предпосылки те же, что у ассистента (см. README.md §1): Ollama с nomic-embed-text и
проиндексированная документация (`python3 main.py ingest`). Для разделов B–E нужен LLM
(DEEPSEEK_API_KEY или `/model local`); разделы A и F работают без LLM.
"""

import os
import sys

import _bootstrap  # noqa: F401 — настраивает sys.path на модули week_5

import llm_provider

from config import SupportConfig
from assistant import answer_support
import crm_context

BAR = "=" * 78
SUB = "-" * 78


def _title(section: str, text: str) -> None:
    print(f"\n{BAR}\n  {section}. {text}\n{BAR}")


def _step(text: str) -> None:
    print(f"\n{SUB}\n{text}\n{SUB}")


def _diag(res: dict) -> str:
    rr = res.get("max_rerank")
    rr_txt = f"{rr:.3f}" if rr is not None else "—"
    return (f"[запрос: {res.get('rewritten_query')!r} | max_cosine: {res.get('max_score', 0.0):.3f}"
            f" | max_rerank: {rr_txt} | контекст CRM: {'да' if res.get('crm_found') else 'нет'}"
            f" | вызов LLM: {'да' if res.get('threshold_passed') else 'НЕТ (отказ)'}]")


def _sources(res: dict, limit: int = 3) -> None:
    if not res.get("sources"):
        return
    print("Источники:")
    for s in res["sources"][:limit]:
        rr = s.get("rerank_score")
        rr_txt = f", rerank={rr:.3f}" if rr is not None else ""
        print(f"  - {s['meta_file']} :: {s['meta_section']} (cosine={s['score']:.3f}{rr_txt})")


def _ask(cfg: SupportConfig, question: str, ticket_id=None, user_id=None, show_sources=True) -> dict:
    tag = f" [тикет {ticket_id}]" if ticket_id else (f" [пользователь {user_id}]" if user_id else " [без контекста]")
    print(f"\nВопрос{tag}: {question}\n")
    res = answer_support(cfg, question, ticket_id=ticket_id, user_id=user_id)
    print(res["answer"].strip() + "\n")
    if show_sources:
        _sources(res)
    print(_diag(res))
    return res


# --------------------------------------------------------------------------- A

def section_a(cfg: SupportConfig) -> None:
    _title("A", "CRM через MCP (без единого вызова LLM)")
    print("Ассистент не читает crm_data/*.json — он поднимает crm_mcp_server.py подпроцессом")
    print("и вызывает его инструменты по stdio. Ниже — чистый MCP, LLM не участвует.")

    _step("Открытые тикеты: crm_list_tickets(status='open')  ->  MCP")
    for t in crm_context.list_tickets(status="open", crm_dir=cfg.crm_dir):
        print(f"  {t['ticket_id']} | {t.get('error_code') or '—':9} | {t.get('user_id')} | {t.get('subject')}")

    _step("Контекст тикета: crm_get_ticket + crm_get_user  ->  MCP")
    print("Именно этот блок подставляется в промпт генерации как «что мы знаем о клиенте».\n")
    print(crm_context.ticket_context("TCK-1042", cfg.crm_dir)["text"])


# --------------------------------------------------------------------------- B

def section_b(cfg: SupportConfig) -> None:
    _title("B", "Ядро задания: один вопрос × три тикета -> три ответа")
    print("Вопрос везде один и тот же. Разница в ответах — только из контекста тикета в CRM.")
    q = "Почему не работает авторизация?"
    for tid, why in [("TCK-1042", "Free + SSO-402"),
                     ("TCK-1043", "AUTH-403 блокировка"),
                     ("TCK-1044", "MFA-401 рассинхрон времени, клиент iOS")]:
        _step(f"{tid} — ожидаем: {why}")
        _ask(cfg, q, ticket_id=tid)


# --------------------------------------------------------------------------- C

def section_c(cfg: SupportConfig) -> None:
    _title("C", "Контекст тикета управляет и ПОИСКОМ, не только ответом")
    print("Сравните переписанный запрос и источники: с тикетом код ошибки и тариф попадают в")
    print("поисковый запрос, и retrieval целится в раздел SSO, а не в общую страницу про вход.")
    q = "Почему не работает авторизация?"
    _step("Без контекста")
    _ask(cfg, q)
    _step("С тикетом TCK-1042 (Free, SSO-402)")
    _ask(cfg, q, ticket_id="TCK-1042")


# --------------------------------------------------------------------------- D

def section_d(cfg: SupportConfig) -> None:
    _title("D", "Тариф решает и в других разделах (не только авторизация)")
    _ask(cfg, "Почему API отдаёт 429?", ticket_id="TCK-1051")


# --------------------------------------------------------------------------- E

def section_e(cfg: SupportConfig) -> None:
    _title("E", "Вопрос вне документации -> отказ, LLM не вызывается")
    print("Порог стоит на rerank-скоре cross-encoder'а (< 0.10 -> отказ). На русском корпусе")
    print("косинус мусор и попадание не различает (обe ~0.74), а rerank различает начисто.")
    _step("Мусорный вопрос без контекста")
    _ask(cfg, "Какая погода в Москве?", show_sources=False)
    _step("Живой вопрос для сравнения (порог пройден, LLM вызван)")
    r = answer_support(cfg, "Как включить двухфакторную аутентификацию?")
    print(f"\nВопрос: Как включить двухфакторную аутентификацию?\n")
    print(r["answer"].strip()[:400] + " …\n")
    print(_diag(r))


# --------------------------------------------------------------------------- F

def section_f(cfg: SupportConfig) -> None:
    _title("F", "Запись в CRM через MCP: заметка в тикет")
    print("Единственный инструмент на запись — crm_add_ticket_note. Демо добавляет заметку,")
    print("показывает, что она сохранилась в JSON, и откатывает данные обратно.")

    tickets_path = os.path.join(cfg.crm_dir, "tickets.json")
    with open(tickets_path, "rb") as fh:
        backup = fh.read()
    try:
        _step("crm_add_ticket_note('TCK-1042', ...)  ->  MCP (запись)")
        print(crm_context.add_note("TCK-1042", "демо: тариф Free, SSO требует Business", cfg.crm_dir))
        _step("Читаем тикет обратно через MCP — заметка на месте")
        block = crm_context.ticket_context("TCK-1042", cfg.crm_dir)["text"]
        marker = "Внутренние заметки поддержки:"
        tail = block.split(marker, 1)[-1].strip() if marker in block else ""
        print(f"{marker}\n{tail}" if tail else "(заметок нет)")
    finally:
        with open(tickets_path, "wb") as fh:
            fh.write(backup)
        print("\n(данные CRM откатаны к исходному состоянию)")


SECTIONS = {
    "A": section_a, "B": section_b, "C": section_c,
    "D": section_d, "E": section_e, "F": section_f,
}


def main(argv: list[str]) -> int:
    cfg = SupportConfig()
    if not os.path.exists(cfg.db_path):
        print(f"Индекс не найден: {cfg.db_path}\nСначала: ../deepseek-env/bin/python main.py ingest")
        return 1

    wanted = [a.upper() for a in argv if a.upper() in SECTIONS] or list(SECTIONS)
    print(f"Ассистент поддержки '{cfg.product_name}' — демо")
    print(f"Провайдер LLM: {llm_provider.current_label()}  |  доступны: {llm_provider.available_providers()}")
    print(f"Разделы: {', '.join(wanted)}")

    for key in wanted:
        SECTIONS[key](cfg)

    print(f"\n{BAR}\n  Демо завершено.\n{BAR}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
