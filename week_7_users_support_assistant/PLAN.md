# PLAN — Ассистент поддержки пользователей

Реализация по SPEC.md. Порядок шагов выбран так, чтобы каждый следующий можно было проверить
сразу после предыдущего.

## Структура каталога

```
week_7_users_support_assistant/
├── SPEC.md
├── PLAN.md
├── README.md                 # как запустить + разбор сценариев
├── _bootstrap.py             # sys.path -> переиспользуемые модули week_5
├── config.py                 # SupportConfig: продукт, каталоги, globs, db
├── product/                  # ВЫМЫШЛЕННЫЙ ПРОДУКТ (корпус RAG)
│   ├── README.md             # обзор TaskPilot, тарифы
│   └── docs/
│       ├── faq.md            # частые вопросы
│       ├── auth_login.md     # вход по паролю, блокировки, сброс
│       ├── auth_sso.md       # SAML SSO, тарифные ограничения
│       ├── auth_mfa.md       # 2FA/TOTP, рассинхрон времени
│       ├── api_keys.md       # API-ключи, rate limits
│       ├── webhooks.md       # вебхуки
│       ├── billing_plans.md  # тарифы и лимиты
│       └── error_codes.md    # справочник кодов ошибок
├── crm_data/                 # ЗАМЕНА CRM
│   ├── users.json            # ~6 пользователей
│   └── tickets.json          # ~8 тикетов
├── crm_mcp_server.py         # MCP-сервер поверх JSON (stdio, FastMCP)
├── crm_mcp_client.py         # stdio-клиент к нему
├── crm_context.py            # MCP-вызовы -> текстовый блок контекста
├── doc_loader.py             # docs -> чанки по заголовкам
├── ingest.py                 # чанки -> эмбеддинги -> SQLite
├── rag.py                    # rewrite-free retrieval: embed -> cosine -> порог -> rerank
├── assistant.py              # оркестрация ответа + генерация
└── main.py                   # CLI: ingest / ask / REPL
```

## Шаги

### Шаг 1 — Каркас и конфиг
- `_bootstrap.py`: пути к `week_5_RAG`, `week_5_RAG/request_to_RAG`,
  `week_5_RAG/reranking_and_rewrite`, `week_5_RAG/chat_with_RAG` (git MCP из week_4 здесь не
  нужен — MCP-сервер свой, локальный).
- `config.py`: `SupportConfig(product_name, product_dir, crm_dir, db_path, table, doc_globs,
  exclude_dirs)`; дефолты указывают на `product/` и `crm_data/` внутри пакета, db —
  `rag_taskpilot.db`.
- Проверка: `python3 -c "import config; print(config.SupportConfig())"`.

### Шаг 2 — Контент продукта (`product/`)
Пишем документацию на русском так, чтобы:
- каждая причина сбоя авторизации жила в **своём** файле (`auth_sso.md`, `auth_login.md`,
  `auth_mfa.md`) — иначе нельзя показать, что тикет направляет retrieval;
- `error_codes.md` связывал коды (`SSO-402`, `AUTH-403`, `MFA-401`, `API-429`) с разделами;
- `billing_plans.md` фиксировал: SSO только на Business, rate limit по тарифам;
- `faq.md` давал общий ответ для сценария без тикета.
Объём: ~40–70 чанков суммарно.
- Проверка: `python3 -c "from config import SupportConfig; from doc_loader import load_chunks; print(len(load_chunks(SupportConfig())))"`.

### Шаг 3 — Данные CRM (`crm_data/`)
- `users.json`: тарифы вразнобой (free/pro/business), поля `sso_enabled`, `mfa_enabled`, `role`.
- `tickets.json`: TCK-1042 (SSO-402, Free), TCK-1043 (AUTH-403), TCK-1044 (MFA-401),
  TCK-1051 (API-429, Pro) + фон (billing, webhooks, closed-тикеты).
- Согласованность обязательна: `error_code` тикета обязан соответствовать тарифу/настройкам
  пользователя, иначе ответы поедут.
- Проверка: `python3 -m json.tool crm_data/tickets.json > /dev/null`.

### Шаг 4 — MCP-сервер и клиент
- `crm_mcp_server.py`: FastMCP `stdio`, загрузка JSON при каждом вызове (правки видны без
  перезапуска), 5 инструментов из SPEC §5, возврат человекочитаемого текста (как git-сервер
  day_17). Путь к данным — env `CRM_DATA_DIR`, дефолт `./crm_data`.
- `crm_mcp_client.py`: `call_crm_tool(name, args)` через `stdio_client` + `ClientSession`,
  по образцу `git_mcp_client.py`.
- Проверка: `python3 crm_mcp_client.py` — печатает список инструментов и карточку TCK-1042.

### Шаг 5 — Контекст CRM для промпта
- `crm_context.py`: `ticket_context(ticket_id)` (тикет + его пользователь + другие открытые
  тикеты этого пользователя), `user_context(user_id)`, `list_tickets(...)`, `add_note(...)`.
- Возвращает и текстовый блок для промпта, и структурированные факты (тариф, код ошибки) —
  факты нужны шагу rewrite.
- Проверка: `python3 -c "import crm_context; print(crm_context.ticket_context('TCK-1042')['text'])"`.

### Шаг 6 — RAG-конвейер
- `doc_loader.py` + `ingest.py` + `rag.py` — по образцу `week_7_assistant`, но корпус берётся
  из `product/` (каталог, не git-репозиторий); префиксы `search_document:`/`search_query:`;
  порог 0.55; top-12 → rerank → top-4.
- Проверка: `python3 main.py ingest`, затем ретрив без LLM.

### Шаг 7 — Ассистент
- `assistant.py`:
  - `_rewrite(question, crm_facts)` — LLM-переписывание запроса **с подмешанным контекстом
    тикета** (код ошибки, product_area, тариф);
  - порог не пройден → отказ + текст эскалации (LLM не вызывается);
  - `answer_support(cfg, question, ticket_id=None, user_id=None)` → dict с `answer`, `sources`,
    `rewritten_query`, `max_score`, `crm_context`, `provider`;
  - системный промпт: отвечать по-русски, только по выданным выдержкам, учитывать тариф и
    настройки пользователя, ссылаться на файлы документации, не выдумывать.
- Проверка: сценарии 1–6 из SPEC §8.

### Шаг 8 — CLI
- `main.py`: `ingest`, `ask [--ticket ID] [--user ID] "вопрос"`, REPL с `/ticket`, `/user`,
  `/tickets`, `/whoami`, `/note`, `/model`, `/quit`; печать ответа, источников и диагностики
  (провайдер, переписанный запрос, max cosine, активный тикет).

### Шаг 9 — Проверка и README
- Прогнать все 6 сценариев, вставить реальный вывод в README.md.
- README: предпосылки (Ollama + `nomic-embed-text`, `DEEPSEEK_API_KEY`, venv `../deepseek-env`),
  запуск, как это работает по шагам, таблица файлов, что переиспользовано.

## Риски

| Риск | Митигация |
|---|---|
| Ollama выключен → пустые эмбеддинги | `ingest` уже падает с внятной ошибкой (RuntimeError), повторяем эту проверку |
| ~~Маленький корпус → косинус ниже порога на нормальных вопросах~~ **Случилось обратное:** русский корпус держит высокий базовый косинус (мусорный вопрос — 0.743 против 0.850 у попадания), порог 0.55 пропускал мусор | **Решено:** решающий порог перенесён на rerank-скор cross-encoder'а (0.10): мусор 0.000, попадание 0.99–1.00. Косинусный порог снижен до 0.50 и оставлен грубым фильтром. См. `rag.py` и SPEC §6 |
| Модель отвечает по-английски | Явное требование языка в системном промпте + русский корпус |
| Тикет не влияет на ответ (RAG отвечает «вообще») | Контекст тикета подмешан и в rewrite (влияет на retrieval), и в промпт генерации; сценарии 2–4 сравниваем между собой |
| Локальная LLM медленная на ноутбуке | Дефолт — DeepSeek; `/model local` остаётся как опция (проверять на VPS) |
