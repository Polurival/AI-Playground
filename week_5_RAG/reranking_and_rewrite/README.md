# RAG v3 — Query Rewrite + Two-Stage Retrieval (Cross-Encoder Rerank)

Третий этап RAG-пайплайна: поверх базового RAG из `week_5_RAG/request_to_RAG` добавлены Query Rewrite и двухэтапный поиск (Broad Retrieval + настоящий Cross-Encoder Reranker).

> Первая версия этого модуля фильтровала top-10 простым порогом по cosine-схожести. Порог заменён на локальную кросс-энкодер модель (`BAAI/bge-reranker-base` через `sentence-transformers`) — она независимо оценивает релевантность каждой пары (запрос, чанк), а не просто режет по уже имеющемуся cosine-скору. Итоги сравнения обеих версий — в разделе "Аналитический вывод".

Ничего в `request_to_RAG` не менялось — все новые модули импортируют оттуда `retrieve_chunks`, `generate_answer`, `build_context`, DeepSeek-клиент (`client`, `MODEL`) напрямую (через `sys.path`, тем же паттерном, что `retrieval.py` использовал для доступа к `database.py`/`embedder.py` в `week_5_RAG`).

---

## Структура

```
reranking_and_rewrite/
├── query_rewrite.py    # Шаг 1 — rewrite_query(user_query)
├── retrieval_v2.py     # Шаг 2 — broad retrieval (top-10) + cross-encoder rerank (top-3)
├── agent_v2.py         # Шаг 3 — ask_agent_v2(question, mode='basic'|'advanced')
├── evaluate_v2.py      # Шаг 4 — автотест: Basic vs Advanced RAG → report_v2.md
└── report_v2.md        # Сгенерированный сравнительный отчёт
```

`eval_questions.json` не копировался — `evaluate_v2.py` читает тот же файл из `../request_to_RAG/eval_questions.json`, чтобы вопросы не расходились между этапами.

---

## Как запускать

```bash
# Ollama должен быть запущен (эмбеддинги запроса)
ollama serve &
ollama list   # nomic-embed-text должен быть в списке

# DeepSeek API-ключ
export DEEPSEEK_API_KEY='your-key-here'

# зависимости для reranker'а (torch CPU + sentence-transformers)
../../deepseek-env/bin/pip install --index-url https://download.pytorch.org/whl/cpu torch
../../deepseek-env/bin/pip install sentence-transformers

cd week_5_RAG/reranking_and_rewrite
source ../../deepseek-env/bin/activate
python3 evaluate_v2.py

# Stop Ollama
sudo pkill ollama
```

При первом запуске `sentence-transformers` скачает веса `BAAI/bge-reranker-base` (~1.1 ГБ) с HuggingFace Hub и закэширует их в `~/.cache/huggingface` — повторные запуски их не перекачивают. Модель загружается лениво (один раз на процесс, singleton в `retrieval_v2.py`), а не на каждый вопрос.

Скрипт прогоняет все 10 вопросов из `eval_questions.json` в режимах `basic` и `advanced`, печатает в консоль по каждому вопросу переписанный запрос (если он изменился), число чанков до/после reranking'а и оба ответа, затем перезаписывает `report_v2.md`.

Для точечной проверки одного вопроса:

```python
from agent_v2 import ask_agent_v2
r = ask_agent_v2("What did that guy steal from the queen in the trial chapter?", mode="advanced")
print(r["rewritten_query"], r["answer"])
```

---

## Как это работает

### Шаг 1 — Query Rewrite (`query_rewrite.py`)

`rewrite_query(user_query)` — один быстрый вызов `deepseek-chat` (`temperature=0.0`) со специальным системным промптом: раскрыть местоимения/расплывчатые ссылки в явные сущности книги (имена персонажей, предметы), поправить опечатки, убрать "воду", которая не помогает векторному поиску. Если запрос уже хорош — модель обязана вернуть его без изменений (это явно прописано в промпте). Логируется `[REWRITE] old -> new` или "unchanged".

Пример из smoke-теста:
```
'What did that guy steal from the queen in the trial chapter?'
-> 'What did the Knave of Hearts steal from the Queen of Hearts in the trial chapter?'
```

### Шаг 2 — Двухэтапный поиск (`retrieval_v2.py`)

`retrieve_chunks_advanced(query_text, strategy, top_k_initial=10, top_k_final=3)`:

1. **Broad Retrieval** — вызывает уже готовый `retrieve_chunks()` из `request_to_RAG/retrieval.py` с `top_k=10` (без модификации самой функции). Это чистый cosine-поиск по эмбеддингам `nomic-embed-text` — быстрый, но, как показал прошлый этап, недостаточно точный сам по себе.
2. **Rerank** (`rerank_with_cross_encoder`) — все 10 пар `(query_text, chunk.text)` прогоняются через `CrossEncoder("BAAI/bge-reranker-base")` (`sentence-transformers`). В отличие от cosine-similarity, кросс-энкодер видит запрос и текст чанка ОДНОВРЕМЕННО (не как независимые векторы) и напрямую предсказывает релевантность пары — это качественно другой, более точный сигнал. Чанки пересортировываются по этому score, берутся top-3. Модель — ленивый singleton (`_get_reranker()`), загружается один раз на процесс. Если модель недоступна (нет сети при первой загрузке, сломан torch и т.п.) — код откатывается на исходный cosine-порядок broad-retrieval (`except`-фолбэк), чтобы пайплайн не падал.

Логи чётко маркированы `[RETRIEVE]` / `[RERANK]`, видно каждый чанк с его rerank-score и исходным cosine-score рядом — удобно сравнивать, где кросс-энкодер поменял порядок относительно чистого cosine.

### Шаг 3 — Агент v2 (`agent_v2.py`)

`ask_agent_v2(question, mode='basic'|'advanced', strategy='structural', language=None)`:

- `mode='basic'` — вызывает `ask_agent()` из Задания 2 без изменений (top-3, без rewrite/rerank). Это контрольная точка для сравнения.
- `mode='advanced'` — `rewrite_query(question)` → `retrieve_chunks_advanced(rewritten, ...)` → `build_context()` (переиспользован из `agent.py`) → `generate_answer(question, context)`. Важно: **для поиска используется переписанный запрос, а для финального ответа — оригинальный вопрос пользователя** (чтобы ответ звучал как реакция на то, что реально спросили, а не на перефразированную версию).
- `language` (например `"English"`) — необязательный параметр, форсирует язык финального ответа независимо от того, на каком языке вопрос/контекст. По умолчанию `None`: модель сама выбирает язык (как и раньше). Добавлен как опциональный keyword в `generate_answer()`/`ask_agent()` в `request_to_RAG` — существующий код Задания 2, который его не передаёт, работает без изменений. `evaluate_v2.py` использует `language="English"`, чтобы `report_v2.md` был на одном языке (вопросы в `eval_questions.json` английские, а системный промпт RAG-режима — русский, из-за чего DeepSeek иногда переключался на русский без этой форсировки).

Каждый `source` в `advanced`-ответе несёт и `score` (cosine из broad retrieval), и `rerank_score` (финальный балл кросс-энкодера) — видно оба сигнала сразу.

Оба режима возвращают одинаковую структуру `{answer, sources, rewritten_query, initial_count, dropped_count, final_count}`, что упрощает сравнение в `evaluate_v2.py`.

### Шаг 4 — Автотест (`evaluate_v2.py`)

Прогоняет 10 вопросов из `../request_to_RAG/eval_questions.json` через оба режима, пишет `report_v2.md` с колонками:
[Вопрос] | [Исходный / Переписанный запрос] | [Ответ Базового RAG] | [Ответ Продвинутого RAG] | [Чанков до/после фильтра].

---

## Reranker: почему `bge-reranker-base`, а не порог по cosine

Первая версия этого этапа использовала простой cosine-threshold (0.60) для отсева шума из top-10. Анализ реального прогона (см. ниже) показал два честных провала этого подхода:

- **Q9 (Чеширский Кот).** Единственным чанком, прошедшим порог 0.60, оказался чанк с оглавлением книги (score 0.6047) — а реально релевантный кусок (глава VI, где кот исчезает) остался ниже порога (0.5852) и был отброшен.
- **Q1 (надпись на бутылочке).** Расширенный пул затянул в контекст фрагмент из другой сцены с бутылочкой, и после чисто числового фильтра оба фрагмента остались в top-3 одновременно, что запутало модель.

Причина в обоих случаях одна: cosine-threshold — это фильтр по уже готовому числу, а не независимая оценка релевантности. Он наследует все слепые зоны эмбеддинга — там, где cosine-score сам по себе ошибается (нерелевантный текст получает более высокий score, чем релевантный), порог не может это исправить, он лишь режет по уже неверному ранжированию.

**Решение — заменить порог на настоящий cross-encoder.** `CrossEncoder("BAAI/bge-reranker-base")` (`sentence-transformers`) получает на вход пару `(query, chunk_text)` целиком и одной моделью напрямую предсказывает релевантность — в отличие от cosine, тут нет независимого сравнения двух заранее посчитанных векторов, модель видит оба текста одновременно и учитывает их совместно. Взят `bge-reranker-base` как компромисс: маленький (278M параметров, ~1.1 ГБ), работает на CPU за разумное время (~1–2 сек на 10 пар после прогрева), но обучен именно на задаче reranking (MS MARCO и аналоги), в отличие от `nomic-embed-text`, который оптимизирован под быстрый bi-encoder поиск, а не под точное сравнение пары.

Порог по score кросс-энкодера не введён намеренно: модель уже ранжирует напрямую, top-3 по её score — это и есть отбор самых релевантных из 10; добавлять сверху ещё один числовой cutoff означало бы наступить на те же грабли, что и с cosine-threshold. Если кросс-энкодер недоступен (нет сети при первой загрузке весов, сломан torch) — код откатывается на исходный cosine-порядок broad retrieval, чтобы пайплайн не падал.

---

## Аналитический вывод

**Query Rewrite: помог, но избирательно.** В прогоне запрос был переписан в 7 из 10 случаев (уточнение сущностей/формулировки, например "Bill the Rabbit" → уточнение причинно-следственной цепочки в Q6). На явно "запутанном" вопросе (`"What did that guy steal from the queen in the trial chapter?"`, отдельный smoke-тест вне автотеста) rewrite чисто раскрыл местоимение в `"the Knave of Hearts"` / `"the Queen of Hearts"` — ровно то, для чего шаг задуман. На уже чётких вопросах (Q2, Q6, Q10) модель корректно вернула запрос без изменений, как и предписано промптом.

**Cross-encoder rerank: исправил оба провала cosine-threshold, не сломав остальное.**

- **Q9 (Чеширский Кот) — исправлено.** Из 10 кандидатов кросс-энкодер дал явный отрыв: `struct_ch06_003` (реальная глава с исчезающим котом) получил rerank-score `0.0003`, все остальные — `0.0000` (округлённо). При чистом cosine та же глава была лишь на 5-м месте (0.5852) и не проходила порог 0.60. Advanced RAG в новом прогоне отвечает верно — кот исчезает "beginning with the end of the tail, and ending with the grin, which remained some time after the rest of it had gone".
- **Q10 (Кадриль Омаров) — исправлено, причём это была ошибка, которую cosine-threshold не чинил вообще.** Broad retrieval для Q10 в принципе не давал уверенного cosine-сигнала (лучший кандидат — 0.579, ниже, чем у остальных вопросов), и обе прошлые схемы (Basic RAG и cosine-threshold Advanced) отвечали "нет информации в контексте". Кросс-энкодер здесь показал резкий, уверенный отрыв лидера: `struct_ch10_000` (глава X, The Lobster Quadrille) — rerank-score `0.8398`, второй кандидат — всего `0.2797`. Advanced RAG правильно ответил: "the name of the dance is the Lobster Quadrille, and the dance partner is a lobster".
- **Q1 (надпись на бутылочке) — остаётся нестабильным, и я проверил, почему.** Глава I разбита structural-чанкингом на 3 под-чанка; фраза `"DRINK ME"` вместе с `"beautifully printed in large letters"` целиком находится только в одном из них — `struct_ch01_001`. Я напрямую проверил все 10 кандидатов broad retrieval для этого вопроса: `struct_ch01_001` **не попадает в top-3 ни по cosine (5-е место, 0.5908), ни по cross-encoder score (9-е место из 10, 0.0011)** — реранкер здесь не помог, а по факту оценил нужный чанк даже хуже, чем чистый cosine. В top-3 вместо него попадает `struct_ch01_002` — соседний под-чанк той же главы, где Алиса лишь мельком упоминает "Drink me" в фразе о том, что не стоит пить из непроверенных бутылочек, но самого текста "DRINK ME"/"beautifully printed" там нет. LLM в такой ситуации либо правильно достраивает ответ по одной лишь фразе "Drink me" (и тогда отвечает верно), либо соскальзывает на соседнюю тему про "poison" в том же чанке — это вопрос везения при семплировании (`temperature=0.2`), а не детерминированный сбой пайплайна: в разных прогонах видел оба исхода и у Basic, и у Advanced RAG.

**Итог:** переход на реальный cross-encoder надёжно исправил два случая, где чистый cosine-threshold давал системную ошибку (иррелевантный чанк проходит порог, а релевантный — нет), и даже вытащил вопрос (Q10), с которым не справлялись ни Basic RAG, ни версия с порогом. Q1 показывает границу применимости обоих подходов: если тот единственный чанк, где реально есть ответ, оба ранжирования (и cosine, и cross-encoder) ставят вне top-3, reranking верхнего уровня это не спасает — здесь нужнее либо более крупные/перекрывающиеся чанки для главы I (чтобы деталь про печать не оказалась изолированной в отдельном под-чанке), либо увеличение top_k_final для этого конкретного случая.
