# Day 16 — Connect to MCP (Google Calendar)

Два скрипта:

- `gcal_mcp_client.py` — асинхронный клиент к официальному MCP-серверу
  Google Calendar (`https://calendarmcp.googleapis.com/mcp/v1`). Авторизация
  через `Authorization: Bearer <token>`, токен берётся из переменной
  окружения `GOOGLE_ACCESS_TOKEN`.
  Транспорт — **Streamable HTTP** (`mcp.client.streamable_http.streamablehttp_client`),
  не legacy SSE: сервер отдаёт `405 Method Not Allowed` на GET-запрос
  классического SSE-транспорта и принимает только POST.
  Две функции:
  - `list_google_calendar_tools()` — `session.list_tools()`, возвращает список инструментов.
  - `call_google_calendar_tool(tool_name, arguments)` — `session.call_tool(...)`,
    реальный вызов инструмента (например `list_events`).
- `agent_with_mcp.py` — чат-агент на DeepSeek (на основе `test_deepseek_task_2.py`)
  с двумя путями работы с Google Calendar:
  1. Фраза вроде "список инструментов google calendar" → прямой вызов
     `list_google_calendar_tools()`, в чат печатается реальный список инструментов сервера.
  2. Любой другой вопрос про календарь (например `"What's on my calendar tomorrow?"`)
     → DeepSeek получает схему реальных MCP-инструментов через OpenAI-style
     function calling (`tools=...`), сам решает, что вызывать, и вычисляет
     конкретные параметры (даты типа "tomorrow" → ISO 8601) на основе текущей
     даты, переданной в системном промпте. Агент выполняет вызов через
     `call_google_calendar_tool`, передаёт результат обратно модели и
     возвращает финальный ответ на естественном языке.

  Прочие вопросы, не связанные с календарём, уходят в DeepSeek как обычно.

## Окружение

Используется существующий venv `deepseek-env` в корне репозитория.

```bash
# из корня репозитория
source deepseek-env/bin/activate

# установить недостающие зависимости (openai уже есть, mcp — новая)
pip install mcp openai

export DEEPSEEK_API_KEY='your-deepseek-key'
export GOOGLE_ACCESS_TOKEN='your-google-oauth-access-token'
```

`GOOGLE_ACCESS_TOKEN` должен быть валидным OAuth2 access token с нужными
Calendar-скоупами (получается отдельно через Google OAuth flow, в скриптах
не реализован). Без токена `list_tools` тоже не выполнится — скрипты сразу
сообщат об ошибке/предупреждении.

## Запуск

Только проверка MCP-сервера (список инструментов в консоль):

```bash
cd week_4_mcp/day_16_connect_to_mcp
python3 gcal_mcp_client.py
```

Чат-агент с интеграцией MCP:

```bash
cd week_4_mcp/day_16_connect_to_mcp
python3 agent_with_mcp.py
```

При старте агент один раз загружает список MCP-инструментов (если
`GOOGLE_ACCESS_TOKEN` задан) и строит function-схему для DeepSeek.

В чате, например:

```
Вы: список инструментов google calendar
Агент: Доступно инструментов Google Calendar: 8
- list_events: ...
- search_events: ...
...
```

```
Вы: What's on my calendar tomorrow?
Агент: <DeepSeek вызывает list_events с вычисленными датами и отвечает по результату>
```

Деактивация окружения после работы:

```bash
deactivate
```
