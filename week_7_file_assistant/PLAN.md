# PLAN — Ассистент для работы с файлами проекта

Реализация по `SPEC.md`. Порядок шагов выбран так, чтобы каждый следующий проверялся сразу
после предыдущего (bottom-up: инструменты → цикл → сценарии).

## Структура каталога

```
week_7_file_assistant/
├── SPEC.md
├── PLAN.md
├── README.md                 # как запустить + разбор сценариев с реальным выводом
├── _bootstrap.py             # sys.path -> переиспользуемые модули week_5
├── config.py                 # FileAssistantConfig: root, globs, exclude, apply-режим
├── sample_project/           # СТЕНД (детерминированный целевой проект)
│   ├── README.md             # намеренно неполный (нет sms_channel)
│   ├── CHANGELOG.md          # секция [Unreleased]
│   ├── notifier/
│   │   ├── __init__.py
│   │   ├── client.py         # class Notifier — центральный компонент
│   │   ├── email_channel.py  # использует Notifier
│   │   ├── sms_channel.py    # использует Notifier (без docstring — нарушение инварианта)
│   │   └── retry.py          # utility, есть TODO
│   └── examples/
│       └── quickstart.py     # использует Notifier
├── file_tools.py             # чистые функции над файлами (list/read/search/write/diff) + guard
├── file_mcp_server.py        # MCP-сервер (FastMCP stdio) поверх file_tools
├── file_mcp_client.py        # stdio-клиент к серверу
├── agent_loop.py             # tool-loop: JSON-протокол поверх chat_completion
├── assistant.py              # системный промпт + оркестрация цели
└── main.py                   # CLI: do / tools / REPL
```

## Шаги

### Шаг 1 — Каркас, конфиг, стенд
- `_bootstrap.py`: пути к `week_5_RAG/chat_with_RAG` (нужен `llm_provider`),
  `week_5_RAG/request_to_RAG` (для его `rag_imports` при импорте провайдера). Git-MCP из
  week_4 здесь не нужен — MCP-сервер свой.
- `config.py`: `FileAssistantConfig(root, name, include_globs, exclude_dirs, apply)`;
  дефолт `root=sample_project/`, `apply=False`.
- `sample_project/`: написать стенд по SPEC §5 так, чтобы:
  - `Notifier` реально импортировался/использовался в `email_channel.py`, `sms_channel.py`,
    `examples/quickstart.py` (≥4 использования для сценария 1);
  - `sms_channel.py` не описан в `README.md` (для сценария 4);
  - `sms_channel.py` без module-docstring, одна публичная функция без docstring, `retry.py`
    содержит `# TODO` (для сценария 2);
  - `CHANGELOG.md` c пустой `## [Unreleased]` (для сценария 3).
- Проверка: `python3 -c "import config; print(config.FileAssistantConfig())"` и `ls sample_project`.

### Шаг 2 — Файловые инструменты (`file_tools.py`)
Чистые функции, всё принимает `root` и относительный путь, с `_safe_path` guard
(resolve + проверка `is_relative_to(root)`; выход за корень → ValueError):
- `list_files(root, glob)` → список относительных путей (с exclude_dirs);
- `read_file(root, path)` → текст с номерами строк (как `Read` формат);
- `search_files(root, pattern, glob)` → `[(path, lineno, line)]` (regex, многофайловый);
- `analyze_project(root)` → dict: кол-во файлов, языки/расширения, точки входа, размеры;
- `write_file(root, path, content)` → пишет на диск, возвращает статус;
- `unified_diff(root, path, new_content)` → строка unified diff (старое vs новое, без записи).
- Проверка: юнит-вызовы из `python3 -c ...` на стенде (поиск Notifier находит 4+ строк;
  guard кидает на `../../etc/passwd`).

### Шаг 3 — MCP-сервер и клиент
- `file_mcp_server.py`: FastMCP `stdio`; 6 инструментов из SPEC §4 как тонкие обёртки над
  `file_tools`; корень берётся из env `FILE_ASSISTANT_ROOT`. `write_file`/`propose_change`
  различаются флагом: `propose_change` всегда возвращает diff без записи; `write_file`
  пишет. Возврат — человекочитаемый текст (как git-сервер day_17).
- `file_mcp_client.py`: `call_file_tool(name, args)` + `list_tools()` через `stdio_client` +
  `ClientSession`, по образцу `git_mcp_client.py`. Прокидывает `FILE_ASSISTANT_ROOT` в env
  подпроцесса.
- Проверка: `python3 file_mcp_client.py` — печатает список инструментов и результат
  `search_files("Notifier")`.

### Шаг 4 — Агентный цикл (`agent_loop.py`)
- Реестр инструментов: имя → (описание, JSON-схема аргументов) для системного промпта.
- `run(system_prompt, goal, call_tool, max_steps=8)`:
  - диалог `messages`, на каждом шаге `llm_provider.chat_completion(messages)`;
  - парсинг ответа как JSON (устойчиво: вырезать первый `{...}`, снять ```json-ограждения);
  - если `{"tool","args"}` → `call_tool(name,args)` → добавить `observation` в messages;
  - если `{"final"}` → вернуть отчёт + трейс шагов;
  - лимит `max_steps`, аккуратные ошибки парсинга/инструмента возвращаются модели как
    observation (self-heal), не роняют процесс.
- Возврат: `{"final": str, "steps": [{"tool","args","observation"}], "changed_files": [...]}`.
- Проверка: подставить фейковый `call_tool`, убедиться что цикл вызывает инструмент и
  завершается на `final`.

### Шаг 5 — Ассистент (`assistant.py`)
- Системный промпт: роль (агент по файлам проекта), список инструментов с сигнатурами,
  строгий JSON-протокол (§3), режим записи (apply/dry-run) — в dry-run модель обязана
  использовать `propose_change` вместо `write_file`, отвечать по-русски, в конце дать
  `final` с кратким отчётом и перечнем `file:line`/изменённых файлов.
- `run_goal(cfg, goal)`: собирает промпт, поднимает MCP-клиент, отдаёт `call_tool` в
  `agent_loop.run`, собирает изменённые файлы/diff, возвращает результат.
- Проверка: сценарии 1–2 (только чтение) на стенде.

### Шаг 6 — CLI (`main.py`)
- `--root`, `--apply`, `-v`; подкоманды `do "<цель>"`, `tools`; без подкоманды — REPL.
- REPL: текст = цель; `/apply on|off`, `/tools`, `/quit`.
- Вывод: трейс шагов (инструмент + краткие аргументы), финальный отчёт, diff или список
  сохранённых файлов. Паттерн печати — из `week_7_assistant/main.py`.
- Проверка: все 6 сценариев из SPEC §8.

### Шаг 7 — Проверка воспроизводимости и README
- Прогнать сценарии 3/4 дважды с `git checkout sample_project` между прогонами → diff
  идентичен (SPEC §8 #6).
- README: предпосылки (venv `../deepseek-env`, `DEEPSEEK_API_KEY`), запуск, «как это работает
  по шагам», таблица файлов, что переиспользовано, разбор каждого сценария с реальным выводом.

## Риски

| Риск | Митигация |
|---|---|
| Модель не держит строгий JSON-протокол | Жёсткий системный промпт + примеры; устойчивый парсер (вырезание `{...}`, снятие ``` ); ошибку парсинга возвращаем модели как observation для самокоррекции |
| Зацикливание агента | `max_steps` (8) + требование `final`; при исчерпании — печать частичного трейса |
| Запись за пределы проекта | `_safe_path` guard в `file_tools` (resolve + is_relative_to root) — единственная точка записи |
| Случайная порча стенда при демо | dry-run по умолчанию; `--apply` осознанный; стенд под git → `git checkout` восстанавливает |
| Локальная модель не тянет tool-loop | Для задания используем только DeepSeek (cloud); локальную LLM не подключаем — см. SPEC §3 |
| DeepSeek native tool-calling vs текстовый протокол | Берём текстовый JSON-протокол, т.к. переиспользуемый `chat_completion` возвращает только строку (без `tools`) — не переписываем провайдер, см. SPEC §3 |
