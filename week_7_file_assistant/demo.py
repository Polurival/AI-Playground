#!/usr/bin/env python3
"""End-to-end demo of the file assistant: five agentic scenarios, in order, on one project.

Runs, against sample_project, the five kinds of task the assistant is built for:

    1. find every usage of a component / API            (read-only)
    2. update documentation from the current code        (APPLY — writes README.md)
    3. generate a brand-new file (ADR/ARCHITECTURE)      (APPLY — writes ARCHITECTURE.md)
    4. check files against invariants / rules            (read-only)
    5. prepare a diff / change-list                      (read-only, propose_change)

Scenarios 2 and 3 run in APPLY mode, so they actually modify / create files on disk — the demo
snapshots the working tree before and after and prints exactly which files were added or changed.

By default it works on a FRESH COPY of sample_project under demo_work/ so the run is repeatable and
the git-tracked stand stays pristine. Pass --in-place to mutate the real sample_project instead.

Usage:
    $PY demo.py                 # copy sample_project -> demo_work/, run all 5 scenarios
    $PY demo.py --in-place      # run against the real sample_project (mutates it)
    $PY demo.py --max-steps 16  # give each scenario a bigger step budget
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys

import _bootstrap  # noqa: F401 — wires sys.path to week_5 llm_provider

import llm_provider

from assistant import run_goal
from config import FileAssistantConfig

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "sample_project")
WORK = os.path.join(HERE, "demo_work", "sample_project")

# component/API the "find usages" and "update docs" scenarios talk about
COMPONENT = "Notifier"

SCENARIOS = [
    {
        "n": 1,
        "title": "Найти все места использования компонента/API",
        "apply": False,
        "goal": (
            f"Найди все места в проекте, где используется компонент {COMPONENT}: определение класса, "
            f"импорты, а также вызовы его методов register и broadcast. Составь список с file:line "
            f"для каждого вхождения."
        ),
    },
    {
        "n": 2,
        "title": "Обновить документацию по изменениям в коде  (APPLY)",
        "apply": True,
        "goal": (
            "Прочитай текущий код каналов и клиента, затем обнови файл README.md так, чтобы он точно "
            "описывал ВСЕ доступные каналы уведомлений (EmailChannel, SmsChannel) и публичный API "
            f"{COMPONENT} (методы register и broadcast) и механизм retry. Сохрани структуру файла, "
            "исправь неточности и добавь недостающее. Запиши изменения через change-инструмент."
        ),
    },
    {
        "n": 3,
        "title": "Сгенерировать новый файл (ARCHITECTURE.md)  (APPLY)",
        "apply": True,
        "goal": (
            "Создай НОВЫЙ файл ARCHITECTURE.md в корне проекта с кратким описанием архитектуры "
            f"библиотеки: центральный компонент {COMPONENT}, протокол Channel, конкретные каналы "
            "(EmailChannel, SmsChannel) и механизм повторов retry. Ссылайся на file:line из кода. "
            "Файл должен быть создан через change-инструмент."
        ),
    },
    {
        "n": 4,
        "title": "Проверить файлы на инварианты/правила",
        "apply": False,
        "goal": (
            "Проверь проект на инварианты: у каждого модуля и каждой публичной функции есть docstring; "
            "нет оставшихся TODO. Составь список нарушений с file:line (или подтверди, что нарушений нет)."
        ),
    },
    {
        "n": 5,
        "title": "Подготовить diff / список изменений",
        "apply": False,
        "goal": (
            "Подготовь список изменений для CHANGELOG.md: на основе недавнего кода предложи новую "
            "запись в начало CHANGELOG.md и покажи её как unified diff через propose_change "
            "(ничего не записывая на диск). В финале перечисли предложенные изменения."
        ),
    },
]


def _fmt_args(args: dict) -> str:
    """Compact one-line rendering of tool args for the trace (truncate big content)."""
    parts = []
    for k, v in args.items():
        s = str(v).replace("\n", "\\n")
        if len(s) > 60:
            s = s[:57] + "..."
        parts.append(f"{k}={s}")
    return ", ".join(parts)


def _print_result(res: dict, mode: str) -> None:
    """Print one scenario's agent trace, any proposed/written diffs, and the final report."""
    print(f"\n--- agent trace ({len(res['steps'])} tool calls, mode={mode}) ---")
    for i, step in enumerate(res["steps"], 1):
        print(f"{i}. {step['tool']}({_fmt_args(step['args'])})")

    diffs = [s for s in res["steps"] if s["tool"] in ("propose_change", "write_file")]
    if diffs:
        heading = "Applied changes" if mode == "apply" else "Proposed changes (dry-run — nothing written)"
        print(f"\n=== {heading} ===")
        for s in diffs:
            print(f"\n# {s['args'].get('path', '?')}")
            print(str(s["observation"]).strip())

    if res.get("changed_files"):
        print(f"\nChanged files (written to disk): {', '.join(res['changed_files'])}")

    print("\n=== Result ===")
    print(res["final"].strip())
    print(f"\n[provider: {res.get('provider')} | steps: {len(res['steps'])}"
          f"{' | STOPPED at max steps' if res.get('stopped') else ''}]")


def _prepare_root(in_place: bool) -> str:
    """Return the project root the demo runs on; copy sample_project unless --in-place."""
    if in_place:
        return SRC
    work_parent = os.path.dirname(WORK)
    if os.path.isdir(work_parent):
        shutil.rmtree(work_parent)
    shutil.copytree(SRC, WORK)
    return WORK


def _snapshot(root: str) -> dict[str, tuple[int, float]]:
    """Map every file under root -> (size, mtime), for before/after change detection."""
    snap: dict[str, tuple[int, float]] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {"__pycache__", ".git"}]
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, root)
            st = os.stat(p)
            snap[rel] = (st.st_size, st.st_mtime)
    return snap


def _report_changes(before: dict, after: dict) -> None:
    added = sorted(set(after) - set(before))
    modified = sorted(p for p in set(after) & set(before) if after[p] != before[p])
    print("\n" + "=" * 70)
    print("ИТОГ: изменения на диске за весь прогон")
    print("=" * 70)
    print(f"Новые файлы   ({len(added)}): " + (", ".join(added) or "(нет)"))
    print(f"Изменённые    ({len(modified)}): " + (", ".join(modified) or "(нет)"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Five-scenario file-assistant demo.")
    parser.add_argument("--in-place", action="store_true",
                        help="mutate the real sample_project instead of a fresh copy")
    parser.add_argument("--max-steps", type=int, default=12, help="step budget per scenario")
    args = parser.parse_args(argv)

    root = _prepare_root(args.in_place)
    print("=" * 70)
    print("ДЕМО: file assistant — 5 сценариев по порядку")
    print("=" * 70)
    print(f"Провайдер: {llm_provider.current_label()}")
    print(f"Рабочий проект: {root}" + ("  (in-place)" if args.in_place else "  (копия sample_project)"))
    print(f"Бюджет шагов на сценарий: {args.max_steps}")

    before = _snapshot(root)

    for sc in SCENARIOS:
        mode = "apply" if sc["apply"] else "dry-run"
        print("\n" + "#" * 70)
        print(f"# Сценарий {sc['n']}: {sc['title']}   [{mode}]")
        print("#" * 70)
        print(f"Цель: {sc['goal']}\n")
        cfg = FileAssistantConfig(root=root, apply=sc["apply"])
        res = run_goal(cfg, sc["goal"], max_steps=args.max_steps)
        _print_result(res, mode)

    after = _snapshot(root)
    _report_changes(before, after)
    if not args.in_place:
        print(f"\nСмотри результат (README.md, ARCHITECTURE.md) в: {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
