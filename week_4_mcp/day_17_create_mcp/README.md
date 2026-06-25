# Day 17 — Create your own MCP server (Git)

В отличие от day_16 (клиент к чужому удалённому MCP-серверу Google Calendar),
здесь реализован **свой** MCP-сервер вокруг Git CLI и клиент/агент к нему.

Три файла:

- `git_mcp_server.py` — собственный MCP-сервер на `FastMCP` (пакет `mcp`).
  Поднимается по **stdio**-транспорту (`mcp.run(transport="stdio")`).
  Регистрирует 5 инструментов, каждый — обёртка над `git` CLI
  (`subprocess.run(["git", "-C", repo_path, ...])`):
  - `git_status(repo_path=".")` — `git status --short --branch`.
  - `git_log(repo_path=".", max_count=10)` — `git log --oneline --decorate`.
  - `git_diff(repo_path=".", staged=False)` — `git diff` / `git diff --staged`.
  - `git_branch_list(repo_path=".")` — `git branch --all`.
  - `git_show_commit(repo_path=".", commit_hash="HEAD")` — `git show <hash>`.

  Входные параметры и их типы/умолчания описаны прямо в сигнатурах функций
  (`repo_path: str = "."`, `max_count: int = 10`, `staged: bool = False`) —
  `FastMCP` сам строит из них JSON Schema (`inputSchema`), docstring идёт
  в `description` инструмента. Результат каждого инструмента — обычная
  строка (stdout команды git или текст ошибки), которую MCP оборачивает
  в `TextContent`.

- `git_mcp_client.py` — асинхронный клиент. В отличие от day_16
  (`streamablehttp_client` к внешнему URL), здесь клиент сам запускает
  `git_mcp_server.py` как **подпроцесс** через `mcp.client.stdio.stdio_client`
  и общается с ним по stdio. Две функции:
  - `list_git_tools()` — `session.list_tools()`.
  - `call_git_tool(tool_name, arguments)` — `session.call_tool(...)`,
    реальный вызов инструмента (например `git_log`).

- `agent_with_mcp.py` — чат-агент на DeepSeek (структура скопирована с
  `day_16/agent_with_mcp.py`), с двумя путями работы с git-инструментами:
  1. Фраза вроде "список инструментов git" → прямой вызов
     `list_git_tools()`, в чат печатается реальный список инструментов сервера.
  2. Любой другой вопрос про репозиторий (например
     `"Покажи последние 3 коммита в этом репозитории"`) → DeepSeek получает
     схему реальных MCP-инструментов через OpenAI-style function calling
     (`tools=...`), сам решает, какой инструмент вызвать и с какими
     параметрами. Агент выполняет вызов через `call_git_tool`, передаёт
     результат обратно модели и возвращает финальный ответ на естественном
     языке.

  По умолчанию агент работает с корнем этого репозитория
  (`DEFAULT_REPO_PATH`), если пользователь не указал другой путь.

## Окружение

Используется существующий venv `deepseek-env` в корне репозитория.

```bash
# из корня репозитория
source deepseek-env/bin/activate

# mcp и openai уже установлены в deepseek-env
export DEEPSEEK_API_KEY='your-deepseek-key'
```

Git должен быть установлен и доступен в `PATH` (обёртка вызывает `git` через
`subprocess`).

## Запуск

Только проверка собственного MCP-сервера (список инструментов + пример
вызова `git_log` на текущем репозитории):

```bash
cd week_4_mcp/day_17_create_mcp
python3 git_mcp_client.py
```

Чат-агент с интеграцией MCP:

```bash
cd week_4_mcp/day_17_create_mcp
python3 agent_with_mcp.py
```

При старте агент один раз загружает список MCP-инструментов и строит
function-схему для DeepSeek (сервер запускается автоматически как
подпроцесс, отдельно поднимать его не нужно).

В чате, например:

```
Вы: список инструментов git
Агент: Доступно инструментов git: 5
- git_status: ...
- git_log: ...
...
```

```
Вы: Покажи последние 3 коммита в этом репозитории
Агент: <DeepSeek вызывает git_log с repo_path и max_count=3, отвечает по результату>
```

```
Вы: Какой статус у репозитория?
Агент: <DeepSeek вызывает git_status и пересказывает вывод>
```

Деактивация окружения после работы:

```bash
deactivate
```
