# Week 7 — Ассистент для работы с файлами проекта (agent + file MCP)

AI-ассистент, который **сам выполняет реальные операции с файлами проекта**. Задаёшь цель на
уровне намерения — «найди все использования компонента», «обнови README под код», «добавь
запись в changelog» — а ассистент **сам решает**, какие файлы прочитать, где искать, что
проанализировать и что изменить. Все файловые операции идут через собственный **MCP-сервер**.

Это не RAG-ответ текстом (как `week_7_assistant`), а **агент с циклом вызова инструментов**:
модель на каждом шаге выбирает инструмент, получает результат и продолжает — до готового
результата. Ничего не хардкодится под один проект: `--root` наводит ассистента на любой каталог.

---

## 1. Что реализовано (сценарии задания)

Задание требует минимум 2 сценария — реализованы 4:

| # | Цель (goal-level) | Тип | Результат |
|---|---|---|---|
| 1 | найти все места использования компонента `Notifier` | чтение/поиск | отчёт `file:line` по 7 файлам |
| 2 | проверить инварианты (docstring у модулей/функций, нет TODO) | чтение/анализ | список нарушений с `file:line` |
| 3 | добавить запись в `CHANGELOG.md` | изменение | unified diff (dry-run) или запись (`--apply`) |
| 4 | обновить `README.md` под реальные каналы в коде | изменение | unified diff / запись |

Каждый прогон работает с 2–7 файлами; изменения показываются как **diff** (по умолчанию) или
**сохраняются на диск** (`--apply`); при temperature=0 результат **воспроизводим**.

---

## 2. Предпосылки

- **Python-окружение** с `mcp` и `openai` — в этом репозитории `../deepseek-env`.
- **`DEEPSEEK_API_KEY`** в окружении. Для задания используется **только DeepSeek** (cloud):
  агентный tool-loop требует стабильного следования протоколу, локальную LLM не подключаем.

```bash
cd /media/polurival/Data/AI-Projects/AI-Playground/week_7_file_assistant
PY=../deepseek-env/bin/python
```

Ollama/эмбеддинги здесь **не нужны** — это не RAG.

---

## 3. Запуск

```bash
# сухой прогон (dry-run): изменения показываются как diff, на диск ничего не пишется
$PY main.py --root sample_project do "найди все места, где используется компонент Notifier"

# с записью на диск
$PY main.py --root sample_project --apply do "добавь в CHANGELOG.md запись про SmsChannel"

# список MCP-инструментов (проверка связи)
$PY main.py --root sample_project tools

# интерактивная сессия
$PY main.py --root sample_project
```

REPL: любой текст = цель; `/apply on|off` — переключить режим записи; `/tools`; `/quit`.

Флаги: `--root` (целевой проект, по умолчанию `sample_project/`), `--apply` (писать на диск),
`--max-steps N` (лимит вызовов инструментов, по умолчанию 12), `-v` (логи агента).

### Демо — все 5 сценариев одним запуском

`demo.py` прогоняет все сценарии задания по порядку на `sample_project`. Сценарии 2 и 3 идут в
режиме **apply** и **реально пишут на диск** (обновляют `README.md`, создают `ARCHITECTURE.md`);
1, 4, 5 — dry-run. Чтобы прогон был воспроизводим, а git-стенд оставался чистым, скрипт работает
на **свежей копии** `sample_project/` в `demo_work/` и в конце печатает, какие файлы добавлены/
изменены.

```bash
# все 5 сценариев на копии sample_project (demo_work/), реальный стенд не трогается
$PY demo.py

# то же, но правки идут прямо в sample_project
$PY demo.py --in-place

# больший бюджет шагов на сценарий (по умолчанию 12)
$PY demo.py --max-steps 16
```

Порядок сценариев: 1) найти использования компонента → 2) обновить документацию под код (**apply**)
→ 3) сгенерировать новый файл `ARCHITECTURE.md` (**apply**) → 4) проверка инвариантов → 5) diff /
список изменений. В конце — сводка:

```
ИТОГ: изменения на диске за весь прогон
Новые файлы   (1): ARCHITECTURE.md
Изменённые    (1): README.md
```

---

## 4. Как это работает (по шагам)

```
do --root sample_project "<цель>"
  1. Старт MCP        file_mcp_client поднимает file_mcp_server (stdio-подпроцесс)
  2. Системный промпт assistant.py   каталог инструментов + JSON-протокол + режим (apply/dry-run)
  3. Агентный цикл    agent_loop.py  LLM -> {"tool":...} -> MCP -> observation -> ... (<= max_steps)
  4. Изменение        write_file (apply) или propose_change (только diff, dry-run)
  5. Финал            LLM -> {"final": "..."} -> печать трейса + diff + отчёт
```

**JSON-протокол вместо native tool-calling.** Переиспользуемый
`week_5_RAG/chat_with_RAG/llm_provider.chat_completion` возвращает только строку (без
`tools`/`tool_calls`), поэтому вызовы инструментов идут текстовым JSON-протоколом (ReAct): модель
отвечает **строго одним JSON** — `{"tool": "...", "args": {...}}` или `{"final": "..."}`. Цикл
парсит его, исполняет инструмент через MCP, возвращает `observation` и снова спрашивает модель.

**Устойчивый парсер** (`agent_loop._extract_json`): снимает только *внешнее* ```` ``` ````
-ограждение (не жадно — внутри контента файла бывают свои ```` ```python ```` блоки), находит
сбалансированный `{...}` c учётом строк, и парсит с `strict=False` — модель пишет многострочное
содержимое файла как обычную строку с реальными переводами строк, что строгий JSON отверг бы.

**Guardrail «финал без изменения».** Если модель заявляет `final`, ни разу не вызвав инструмент
изменения, цикл один раз просит её либо реально вызвать `propose_change`/`write_file`, либо
подтвердить, что задача только на чтение. Ловит «я обновил файл» без фактической правки.

**Два режима записи.** По умолчанию — **dry-run**: правки показываются как unified diff,
на диск ничего не пишется (модели выдаётся только `propose_change`, а `write_file`
перехватывается и в `assistant._make_call_tool` — защита в глубину). С `--apply` — `write_file`
реально пишет. Так закрыты оба варианта задания: «сохраняются **или** выводятся как diff».

**Безопасность.** Все пути — относительно `--root`; `file_tools._safe_path` резолвит их и
отклоняет выход за корень (path traversal). Это единственная точка чтения и записи.

---

## 5. Примеры вывода

### Сценарий 1 — найти все использования `Notifier` (чтение)

```
$PY main.py --root sample_project do "найди все места, где используется компонент Notifier, и составь отчёт"
```

```
--- agent trace (6 tool calls, mode=dry-run) ---
1. search_files(pattern=Notifier, glob=**/*)
2. read_file(path=notifier/client.py)
3. read_file(path=notifier/email_channel.py)
4. read_file(path=notifier/sms_channel.py)
5. read_file(path=examples/quickstart.py)
6. read_file(path=notifier/__init__.py)

=== Result ===
## Отчёт об использовании компонента `Notifier`
Компонент `Notifier` определён в `notifier/client.py` (строка 19) и экспортируется через
`notifier/__init__.py` (строка 3).
Места использования: email_channel.py:23, sms_channel.py:20, examples/quickstart.py:9 ...
```

### Сценарий 2 — проверка инвариантов (анализ)

```
$PY main.py --root sample_project do "проверь проект на инварианты: у каждого модуля и каждой публичной функции есть docstring; нет оставшихся TODO. Составь список нарушений с file:line"
```

```
=== Result ===
1. Отсутствует docstring у модуля — notifier/sms_channel.py:1
2. Отсутствует docstring у публичной функции — notifier/sms_channel.py:20 (register_sms)
3. Оставшийся TODO — notifier/retry.py:13
```

(Все три нарушения намеренно заложены в стенде — см. §6.)

### Сценарий 3 — запись в CHANGELOG (изменение, dry-run)

```
$PY main.py --root sample_project do "добавь в CHANGELOG.md запись в секцию [Unreleased] про добавленный канал SmsChannel и helper register_sms"
```

```
=== Proposed changes (dry-run — nothing written) ===
# CHANGELOG.md
--- a/CHANGELOG.md
+++ b/CHANGELOG.md
@@ -5,6 +5,9 @@
 ## [Unreleased]
 
+### Added
+- `SmsChannel` and `register_sms` helper for SMS notifications.
+
 ## [0.1.0] - 2026-06-01
```

С `--apply` тот же diff **и файл реально изменяется** на диске (в трейсе `write_file`,
`overwrote CHANGELOG.md`, блок `Changed files (written to disk)`).

### Сценарий 4 — обновить README под каналы в коде (изменение)

```
$PY main.py --root sample_project do "обнови README.md так, чтобы раздел Channels описывал все каналы уведомлений, реально существующие в коде"
```

```
--- a/README.md
+++ b/README.md
@@ -14,17 +14,20 @@
 ```python
 from notifier import Notifier
 from notifier.email_channel import register_email
+from notifier.sms_channel import register_sms
 ...
 ## Channels
 - **EmailChannel** (`notifier.email_channel`) — delivers over SMTP.
+- **SmsChannel** (`notifier.sms_channel`) — delivers as SMS text messages.
```

Обрати внимание: агент корректно правит README, **сохраняя вложенные ```` ```python ````
блоки** — ровно тот случай, ради которого исправлен парсер JSON (§4).

### Воспроизводимость

```bash
# два прогона сценария 3 подряд -> идентичный diff (temperature=0)
diff <(run1) <(run2)   # IDENTICAL
```

Стенд под git: после `--apply` восстанавливается `git checkout sample_project`.

---

## 6. Стенд `sample_project/`

Маленькая библиотека уведомлений — детерминированная мишень для воспроизводимого демо. Свойства
заложены под сценарии:

- `Notifier` (в `notifier/client.py`) используется в 4+ местах → сценарий 1 многофайловый;
- `sms_channel.py` **не описан** в README → сценарий 4;
- `sms_channel.py` **без module-docstring**, `register_sms` **без docstring**, в `retry.py`
  есть `# TODO` → сценарий 2 находит ровно эти 3 нарушения;
- `CHANGELOG.md` c пустой секцией `## [Unreleased]` → сценарий 3.

Ассистент project-agnostic: наведи `--root` на любой каталог — стенд лишь дефолт.

---

## 7. Файлы

| Файл | Роль |
|---|---|
| `config.py` | `FileAssistantConfig` — корень проекта, globs, режим apply |
| `file_tools.py` | чистые операции над файлами (list/read/search/analyze/write/diff) + guard `_safe_path` |
| `file_mcp_server.py` | MCP-сервер (FastMCP stdio): 7 файловых инструментов (вкл. batch `read_files`) |
| `file_mcp_client.py` | stdio-клиент к серверу |
| `agent_loop.py` | агентный цикл: JSON-протокол поверх `chat_completion` + парсер + guardrail |
| `assistant.py` | системный промпт (каталог инструментов, протокол, режим) + оркестрация цели |
| `main.py` | CLI: `do` / `tools` / REPL; печать трейса, diff, отчёта |
| `demo.py` | демо-прогон всех 5 сценариев по порядку на копии `sample_project/` |
| `_bootstrap.py` | `sys.path` → переиспользуемый `llm_provider` из week_5 |
| `sample_project/` | детерминированный стенд-мишень |

## 8. Переиспользование (ничего не написано заново)

- `week_5_RAG/chat_with_RAG/llm_provider` — `chat_completion` (провайдер DeepSeek);
- `week_4_mcp/day_17_create_mcp` — образец MCP-сервера (FastMCP stdio) и stdio-клиента;
- `week_7_assistant` — форма пакета (`_bootstrap.py`, `config.py`, `main.py`, REPL, вывод).

Новое здесь: **агентный tool-loop** (JSON-протокол поверх текстового `chat_completion`) и
**MCP-инструменты записи файлов** с dry-run/diff.
