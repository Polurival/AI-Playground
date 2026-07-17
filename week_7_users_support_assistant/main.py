#!/usr/bin/env python3
"""CLI мини-сервиса поддержки пользователей (RAG по документации + CRM через MCP).

Использование:
    # 1) проиндексировать документацию продукта (один раз, и после правок документации)
    python3 main.py ingest

    # 2а) один вопрос без контекста клиента
    python3 main.py ask "Почему не работает авторизация?"

    # 2б) тот же вопрос с контекстом тикета — ответ учитывает тариф и код ошибки из CRM
    python3 main.py ask --ticket TCK-1042 "Почему не работает авторизация?"

    # 2в) с контекстом пользователя
    python3 main.py ask --user USR-004 "Можно ли включить SSO?"

    # 3) интерактивный режим
    python3 main.py
        /ticket TCK-1042        # закрепить тикет как контекст
        почему не работает авторизация?
        /tickets open           # список открытых тикетов
        /note проверил тариф    # записать заметку в тикет (через MCP)
        /model local|deepseek   # переключить LLM
        /quit
"""

import argparse
import logging
import sys

import _bootstrap  # noqa: F401 — настраивает sys.path на модули week_5

import llm_provider

from config import SupportConfig
from ingest import ingest_product
from assistant import answer_support
import crm_context


def _print_result(res: dict) -> None:
    print("\n" + res["answer"].strip() + "\n")
    if res.get("sources"):
        print("Источники:")
        for s in res["sources"]:
            rr = s.get("rerank_score")
            rr_txt = f", rerank={rr:.3f}" if rr is not None else ""
            print(f"  - {s['meta_file']} :: {s['meta_section']} (cosine={s['score']:.3f}{rr_txt})")
    rr = res.get("max_rerank")
    rr_txt = f"{rr:.3f}" if rr is not None else "—"
    print(f"\n[провайдер: {res.get('provider')} | запрос: {res.get('rewritten_query')!r} | "
          f"max_cosine: {res.get('max_score', 0.0):.3f} | max_rerank: {rr_txt} | "
          f"контекст CRM: {'да' if res.get('crm_found') else 'нет'}]")


def _print_tickets(rows: list[dict]) -> None:
    if not rows:
        print("Тикеты не найдены.")
        return
    for t in rows:
        print(f"  {t['ticket_id']} | {t.get('status', '—'):7} | {t.get('error_code') or '—':9} | "
              f"{t.get('user_id', '—')} | {t.get('subject', '')}")


def _repl(cfg: SupportConfig) -> None:
    print(f"Ассистент поддержки '{cfg.product_name}'  (документация: {cfg.db_path})")
    print(f"CRM через MCP: {cfg.crm_dir}")
    print(f"Провайдер: {llm_provider.current_label()}  |  доступны: {llm_provider.available_providers()}")
    print("Команды: /ticket <ID>  /user <ID>  /tickets [status]  /whoami  /note <текст>  "
          "/model <local|deepseek>  /quit")
    print("Обычный текст — вопрос в текущем контексте.\n")

    ticket_id: str | None = None
    user_id: str | None = None

    while True:
        prompt = f"{ticket_id or user_id or 'поддержка'}> "
        try:
            line = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line in ("/quit", "/exit", "/q"):
            break

        # /tickets проверяется раньше /ticket: иначе префикс перехватит список тикетов.
        if line.startswith("/tickets"):
            parts = line.split(maxsplit=1)
            status = parts[1].strip() if len(parts) == 2 else ""
            _print_tickets(crm_context.list_tickets(status=status, crm_dir=cfg.crm_dir))
            continue

        if line.startswith("/ticket"):
            parts = line.split(maxsplit=1)
            if len(parts) != 2:
                print("использование: /ticket TCK-1042")
                continue
            crm = crm_context.ticket_context(parts[1].strip(), cfg.crm_dir)
            if not crm["found"]:
                print(crm["reason"])
                continue
            ticket_id, user_id = crm["facts"]["ticket_id"], None
            print(f"\n{crm['text']}\n")
            continue

        if line.startswith("/user"):
            parts = line.split(maxsplit=1)
            if len(parts) != 2:
                print("использование: /user USR-004")
                continue
            crm = crm_context.user_context(parts[1].strip(), cfg.crm_dir)
            if not crm["found"]:
                print(crm["reason"])
                continue
            user_id, ticket_id = crm["facts"]["user_id"], None
            print(f"\n{crm['text']}\n")
            continue

        if line == "/whoami":
            if ticket_id:
                print(crm_context.ticket_context(ticket_id, cfg.crm_dir)["text"])
            elif user_id:
                print(crm_context.user_context(user_id, cfg.crm_dir)["text"])
            else:
                print("Контекст не задан: /ticket <ID> или /user <ID>")
            continue

        if line.startswith("/note"):
            note = line[len("/note"):].strip()
            if not ticket_id:
                print("сначала закрепите тикет: /ticket TCK-1042")
                continue
            if not note:
                print("использование: /note <текст заметки>")
                continue
            print(crm_context.add_note(ticket_id, note, cfg.crm_dir))
            continue

        if line.startswith("/model"):
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                try:
                    print("переключено ->", llm_provider.set_provider(parts[1]))
                except ValueError as exc:
                    print("ошибка:", exc)
            else:
                print("текущий:", llm_provider.current_label())
            continue

        if line.startswith("/"):
            print("неизвестная команда")
            continue

        _print_result(answer_support(cfg, line, ticket_id=ticket_id, user_id=user_id))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ассистент поддержки пользователей: RAG по документации + CRM через MCP."
    )
    parser.add_argument("--product", default="TaskPilot", help="название продукта (метка и имя индекса)")
    parser.add_argument("--product-dir", default="", help="каталог документации продукта")
    parser.add_argument("--crm-dir", default="", help="каталог JSON-данных CRM")
    parser.add_argument("--db", default="", help="переопределить путь к sqlite-индексу")
    parser.add_argument("-v", "--verbose", action="store_true", help="показывать логи конвейера")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("ingest", help="проиндексировать документацию продукта")
    p_ask = sub.add_parser("ask", help="ответить на один вопрос")
    p_ask.add_argument("--ticket", default="", help="ID тикета: ответ учтёт его контекст")
    p_ask.add_argument("--user", default="", help="ID пользователя: ответ учтёт его карточку")
    p_ask.add_argument("question", nargs="+", help="вопрос пользователя")

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    kwargs = {"product_name": args.product, "db_path": args.db}
    if args.product_dir:
        kwargs["product_dir"] = args.product_dir
    if args.crm_dir:
        kwargs["crm_dir"] = args.crm_dir
    cfg = SupportConfig(**kwargs)

    if args.command == "ingest":
        n = ingest_product(cfg)
        print(f"Проиндексировано {n} чанков документации '{cfg.product_name}' -> {cfg.db_path}")
        return 0
    if args.command == "ask":
        _print_result(answer_support(
            cfg, " ".join(args.question),
            ticket_id=args.ticket or None,
            user_id=args.user or None,
        ))
        return 0
    _repl(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
