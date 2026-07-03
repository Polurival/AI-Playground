# RAG-агент — Alice's Adventures in Wonderland

Второй этап RAG-пайплайна поверх `week_5_RAG`: полноценный агент, который отвечает на вопросы по книге либо напрямую через LLM, либо с опорой на найденные в SQLite чанки (retrieval-augmented generation).

Использует уже готовую БД `../rag_wonderland.db` (эмбеддинги `nomic-embed-text` из первого этапа) и DeepSeek (`deepseek-chat`) как генеративную LLM.

---

## Структура

```
request_to_RAG/
├── retrieval.py        # Шаг 1 — векторный поиск (retrieve_chunks)
├── generation.py       # Шаг 2 — вызов DeepSeek (generate_answer)
├── agent.py            # Шаг 3 — ask_agent(question, use_rag, strategy)
├── eval_questions.json # Шаг 4 — 10 контрольных вопросов с ground truth
├── evaluate.py          # Шаг 5 — автотест: НЕ-RAG vs RAG → report.md
├── main_rag.py          # Демо-скрипт (CLI, оба режима)
└── report.md            # Сгенерированный отчёт (создаётся evaluate.py)
```

`database.py` и `embedder.py` не копировались — модули импортируются напрямую из родительской папки `week_5_RAG` (см. "Как это работает" ниже).

---

## Как запускать

### 0. Подготовка

```bash
# Ollama должен быть запущен (модель для эмбеддингов запроса)
ollama serve &
ollama list   # nomic-embed-text должен быть в списке

# DeepSeek API-ключ
export DEEPSEEK_API_KEY='your-key-here'

# зависимости (venv deepseek-env в корне репозитория)
../../deepseek-env/bin/pip install openai requests
```

### 1. Главный демо-скрипт

```bash
cd week_5_RAG/request_to_RAG
source ../../deepseek-env/bin/activate
python3 main_rag.py
```

Скрипт сначала прогоняет 3 встроенных вопроса в обоих режимах (БЕЗ RAG / С RAG) с логами найденных чанков, затем переходит в интерактивный режим — можно вводить свои вопросы. Выход: `exit` / `quit`.

### 2. Автотест (10 контрольных вопросов)

```bash
cd week_5_RAG/request_to_RAG
source ../../deepseek-env/bin/activate
python3 evaluate.py
```

Прогоняет все вопросы из `eval_questions.json` в режиме БЕЗ RAG и С RAG (стратегия `structural`), печатает сравнение в консоль и перезаписывает `report.md` — таблицу [Вопрос | Ожидание | Ответ без RAG | Ответ с RAG | Источники].

Оба скрипта можно запускать и из любой другой директории (пути к БД/JSON/отчёту резолвятся относительно расположения файлов, а не текущей директории).

---

## Как это работает

### Шаг 1 — Retrieval (`retrieval.py`)

`retrieve_chunks(query_text, strategy, top_k=3)`:

1. Отправляет `query_text` в Ollama (`nomic-embed-text`) через `embedder.get_embedding()` → вектор запроса (768 чисел).
2. Загружает из SQLite все чанки нужной стратегии (`chunks_fixed` или `chunks_structural`) через `database.load_chunks()`, включая уже сохранённые эмбеддинги.
3. Считает косинусное сходство query-вектора с каждым чанком (`cosine_similarity`, чистый `math`, без numpy).
4. Сортирует по убыванию сходства, возвращает top-K вместе с текстом и метаданными (`chunk_id`, `meta_section`, `score` и т.д.).

Модули `database.py` и `embedder.py` физически лежат в `week_5_RAG/`, на уровень выше. `retrieval.py` при импорте добавляет родительскую папку в `sys.path` и берёт путь к `rag_wonderland.db` абсолютным (`os.path.dirname(__file__)/..`), поэтому импорты и путь к БД работают независимо от того, откуда запущен скрипт.

### Шаг 2 — Generation (`generation.py`)

`generate_answer(question, context=None)` — обёртка над `openai.OpenAI(base_url="https://api.deepseek.com")`, модель `deepseek-chat` (тот же паттерн, что в `week_4_mcp/day_18_periodic_mcp/agent_with_mcp.py`).

- Если `context` не передан → используется мягкий системный промпт, вопрос уходит в LLM как есть (режим БЕЗ RAG).
- Если `context` передан → используется строгий системный промпт:
  > «Ты полезный ассистент. Отвечай на вопрос пользователя, основываясь ТОЛЬКО на предоставленном контексте. Если в контексте нет ответа, честно скажи, что не знаешь его, и не придумывай факты.»

  В user-сообщение подставляется `Контекст: ...` + вопрос.

### Шаг 3 — Агент (`agent.py`)

`ask_agent(question, use_rag=True, strategy='structural', top_k=3)`:

- `use_rag=False` → вопрос летит прямо в `generate_answer` без контекста.
- `use_rag=True` → сначала `retrieve_chunks(question, strategy, top_k)`, найденные чанки склеиваются в единый текст (`[раздел]\nтекст`, разделены `---`), передаются в `generate_answer` как контекст. Если ничего не нашлось (например, Ollama недоступна) — фолбэк на ответ без RAG.

Возвращает `{"answer": str, "sources": list[dict]}` — `sources` содержит `chunk_id`, `meta_section`, `score` для каждого использованного чанка (для логов/отчёта).

### Шаг 4 — Контрольные вопросы (`eval_questions.json`)

10 вопросов по книге, каждый факт сверен напрямую с текстом epub (не придуман):

1. Надпись на бутылочке ("DRINK ME")
2. Надпись на пирожном ("EAT ME", выложена изюмом)
3. Что украл Валет Червей (тарты)
4. Цвет Гусеницы (синяя)
5. Какие две стороны гриба меняют рост
6. Имя ящерки, которую посылали в трубу (Билл)
7. Что случилось с карандашом присяжного на суде
8. Необычные школьные предметы Мнимой Черепахи
9. Как исчезает Чеширский Кот (улыбка остаётся последней)
10. Название танца Грифона и Мнимой Черепахи (Lobster Quadrille)

Вопросы намеренно на английском: корпус (эпаб) и эмбеддинги — английские, а `nomic-embed-text` плохо работает cross-lingual — русские запросы давали заметно худший retrieval (нужная глава не попадала в top-3). Для каждого вопроса записаны ключевые факты (ground truth) и ожидаемые главы-источники.

### Шаг 5 — Автотест (`evaluate.py`)

Для каждого вопроса из `eval_questions.json`:

1. `ask_agent(question, use_rag=False)` — ответ без RAG.
2. `ask_agent(question, use_rag=True, strategy='structural')` — ответ с RAG (стратегия `structural` выбрана как лучшая по выводам `analysis.py` из первого этапа: один чанк = одна глава, сохраняет цельность сцены).
3. Строка таблицы: вопрос, ground truth, ответ без RAG, ответ с RAG, источники (`meta_section`, `chunk_id`, `score`).

Результат печатается в консоль и пишется в `report.md`.

**Что показал прогон:** в двух случаях из десяти (Q4, Q10) retrieval не подтянул нужную главу в top-3 — RAG-режим честно ответил «в контексте нет информации» вместо того, чтобы придумать факт. При этом БЕЗ RAG модель в одном из этих случаев (Q10, танец) дала неверный ответ («партнёр по танцу — Грифон», хотя на самом деле это омар/lobster) — типичная галлюцинация, которую и должен предотвращать RAG-режим со строгим промптом.

### Логирование

`retrieve_chunks` логирует найденные чанки (`[score] chunk_id — meta_section`) на уровне INFO — видно в консоли при запуске `main_rag.py` / `evaluate.py`, что именно система достала из базы для каждого запроса.
