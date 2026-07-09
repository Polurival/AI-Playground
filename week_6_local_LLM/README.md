# Week 6 — Локальная LLM

Запуск локальной LLM на ноутбуке. Модель работает **полностью локально** (без облака,
без API-ключей, без сети), к ней можно обращаться через CLI, через прямой HTTP API и
через OpenAI SDK.

## Выбор модели

Железо ноутбука:


| Параметр | Значение                                                         |
| -------- | ---------------------------------------------------------------- |
| CPU      | AMD Ryzen 5 3550H, 8 потоков                                     |
| RAM      | 14 GB (≈7.5 GB свободно)                                         |
| GPU      | Radeon Vega Mobile (интегрированная, без CUDA → инференс на CPU) |


Без дискретной GPU инференс идёт на CPU, поэтому большие модели (7B+) будут медленными и
могут не влезть в память. Выбрана `qwen2.5:3b` (3B параметров, квантизация Q4, ~1.9 GB):

- уверенно помещается в свободную RAM, отвечает за 10–50 с на CPU;
- одна из сильнейших моделей в своём размере (код, рассуждения, факты);
- хорошая мультиязычность, включая русский.

Движок — **Ollama** (уже установлен как snap). Ollama поднимает HTTP-сервер на
`http://localhost:11434` и, что удобно, отдаёт **OpenAI-совместимый** эндпоинт на `/v1` —
поэтому тот же `openai` SDK, что и в `test_deepseek_task_2.py`, работает без изменений,
достаточно поменять `base_url` и `model`.

## Установка и запуск

```bash
# 1. Ollama (snap уже стоял; иначе):
sudo snap install ollama

# 2. Запустить локальный сервер (демон snap слушает localhost:11434):
sudo snap start ollama          # для не-snap сборки: ollama serve

How to stop:

sudo snap stop ollama

Runs ollama.listener again on next boot (service enabled). Kill that autostart too:

sudo snap stop --disable ollama     # stop now + no autostart on boot
sudo snap start --enable ollama     # undo: start + autostart back

Check state:

snap services ollama                # Current: active/inactive, Startup: enabled/disabled

Free RAM without stopping daemon â just unload model:

ollama stop qwen2.5:3b              # evicts model from memory, server stays up

# 3. Скачать модель (~1.9 GB, разово):
ollama pull qwen2.5:3b

# 4. Проверить:
ollama list
curl -s http://localhost:11434/api/version      # {"version":"0.24.0"}
```

Скрипт `local_llm_chat.py` переиспользует существующий venv с `openai` SDK:

```bash
cd week_6_local_LLM
source ../deepseek-env/bin/activate
python3 local_llm_chat.py "What is Python?"
```



## Три способа обращения (CLI + HTTP)

**1. Нативный CLI**

```bash
ollama run qwen2.5:3b "In one sentence: what is an LLM?"
# → An LLM (Large Language Model) is an advanced AI model designed to
#   generate human-like responses across many languages and domains.
```

**2. Прямой HTTP API (curl, без SDK)**

```bash
curl -s http://localhost:11434/api/chat -d '{
  "model": "qwen2.5:3b",
  "messages": [{"role":"user","content":"Say hello in 3 languages, one line."}],
  "stream": false
}'
# → English: Hello.  Spanish: Hola.  French: Bonjour.
```

**3. HTTP через OpenAI SDK** — `local_llm_chat.py` (аналог `test_deepseek_task_2.py`,
только `base_url=http://localhost:11434/v1`, `model=qwen2.5:3b`, без API-ключа).

## Три запроса разной сложности

Все запросы выполнены через `local_llm_chat.py` (HTTP → локальная модель).

### 1. Простой — факт

```bash
python3 local_llm_chat.py "What is the capital of France? Answer in one word." \
  --temperature 0.2 --max-tokens 50
```

```
A: Paris
```

⏱ ~10 с (первый вызов включает загрузку модели в RAM).

### 2. Средний — генерация кода

```bash
python3 local_llm_chat.py "Write a Python function is_prime(n) that returns True if n is prime. Include a one-line docstring. Code only." \
  --temperature 0.2 --max-tokens 250
```

```python
def is_prime(n):
    """Check if the given number n is a prime number."""
    if n <= 1:
        return False
    elif n <= 3:
        return True
    elif n % 2 == 0 or n % 3 == 0:
        return False
    i = 5
    while i * i <= n:
        if n % i == 0 or n % (i + 2) == 0:
            return False
        i += 6
    return True
```

✅ Корректно, с оптимизацией проверки делителей вида 6k±1. ⏱ ~21 с.

### 3. Сложный — многошаговое рассуждение

```bash
python3 local_llm_chat.py "A train leaves at 14:45 and arrives at 17:20. It stopped twice for 8 minutes each. How many minutes was it actually moving? Show your steps." \
  --temperature 0.3 --max-tokens 400
```

```
Step 1. Total travel time: 17:20 − 14:45 = 2 h 35 min = 155 min
Step 2. Total stops: 2 × 8 = 16 min
Step 3. Moving time: 155 − 16 = 139 min
→ The train was actually moving for 139 minutes.
```

✅ Рассуждение и ответ (139 мин) верны. ⏱ ~50 с.

## Оптимизация под кейс: короткие фактические ответы (Q&A)

Кейс: модель должна давать короткий точный ответ на фактический вопрос (даты, числа,
названия) без "воды" — вступлений, оговорок, лишних пояснений.

### Что изменено

**1. Параметры.** Дефолты `local_llm_chat.py` пересчитаны под кейс:


| Параметр                   | Было                 | Стало | Зачем                                                  |
| -------------------------- | -------------------- | ----- | ------------------------------------------------------ |
| `temperature`              | 0.7                  | 0.2   | детерминизм, меньше "фантазии" в фактах                |
| `max_tokens`               | 500                  | 150   | факт короткий, не нужен запас на длинный текст         |
| `num_ctx` (context window) | 4096 (дефолт Ollama) | 1024  | однократный вопрос без истории — большое окно не нужно |


**2. Квантование.** Новых моделей не скачивал — `qwen2.5:3b` уже квантована в Q4_K_M
(`ollama show qwen2.5:3b`), это ≈4x меньше и быстрее гипотетической F16-версии (~7 GB).
Дальше квантовать те же веса без исходников большей точности нельзя, поэтому Q4_K_M
зафиксирован как есть — это и есть применённая оптимизация по этому пункту.

**3. Prompt-шаблон.** System prompt заменён с дженерик `"You are a helpful assistant"` на
прицельный под факты: без вступлений, без оговорок ("I think", "it's worth noting"),
"just the fact" в 1–2 предложениях.

**4. Как это применено.** `num_ctx` **не работает через** `--ctx`**-флаг на каждый запрос** —
Ollama 0.24.0 игнорирует `num_ctx`, переданный через `extra_body` в OpenAI-совместимый
`/v1`-эндпоинт (проверено через `ollama ps`: колонка CONTEXT не менялась). Нативный
`/api/chat` это поддерживает, но `local_llm_chat.py` держится на `openai` SDK. Решение —
`num_ctx`, `temperature` и system prompt зашиты в отдельную **локальную производную
модель** через `Modelfile` (`FROM qwen2.5:3b`, без скачивания — `ollama create` переиспользует
уже скачанные слои весов):

```bash
cp Modelfile ~/qwen_qa.Modelfile   # ollama-snap не видит /media, только $HOME
ollama create qwen2.5-3b-qa -f ~/qwen_qa.Modelfile
rm ~/qwen_qa.Modelfile
```

`local_llm_chat.py` теперь по умолчанию обращается к `qwen2.5-3b-qa`.

### Сравнение до / после

*8 фактических вопросов (*`benchmark.py`*), одна и та же модель* `qwen2.5:3b`*, разные
конфиги — "before" (исходный дженерик-конфиг скрипта) vs "after" (*`qwen2.5-3b-qa`*)*:


| Метрика           | До           | После                         |
| ----------------- | ------------ | ----------------------------- |
| Точность          | 8/8 (100%)   | 8/8 (100%)                    |
| Средняя задержка  | 4.4 с/вопрос | 2.7 с/вопрос (**-39%**)       |
| Токенов/с         | 8.7          | 3.5                           |
| Длина ответа      | 27.0 слов    | 6.4 слова (**в 4.2× короче**) |
| Context window    | 4096         | 1024                          |
| RAM (`ollama ps`) | 2.1 GB       | 2.0 GB                        |


Точность не изменилась (обе конфигурации ответили верно на все 8 вопросов) — оптимизация
не жертвует качеством. Выигрыш: заметно быстрее (короче генерация — меньше токенов
считать) и ответы формата "просто факт" вместо абзаца с оговорками, что и было целью
кейса. Токенов/с ниже "после" — ожидаемо: короткие ответы менее эффективно амортизируют
фиксированный оверхед (eval init) на токен, это не проблема, т.к. итоговая задержка всё
равно меньше. RAM почти не изменился — footprint определяется в основном весами модели
(2 GB), а не KV-кэшем при таком размере ctx.

Воспроизвести: `python3 benchmark.py` (нужен запущенный Ollama и обе модели —
`qwen2.5:3b` и `qwen2.5-3b-qa`, см. Modelfile).

## Результат

Локальная LLM `qwen2.5:3b` запущена на ноутбуке через Ollama, доступна через CLI, прямой
HTTP API и OpenAI SDK, и корректно отвечает на запросы трёх уровней сложности (факт,
код, многошаговое рассуждение) — без облака и без интернета.

Под конкретный кейс (короткие фактические Q&A) модель дополнительно оптимизирована:
параметры (temperature/max_tokens/context window) и prompt-шаблон настроены и зафиксированы
в отдельной локальной модели `qwen2.5-3b-qa` (Modelfile, без переобучения/докачки весов).
Бенчмарк на 8 вопросах показывает то же качество (8/8) при на 39% меньшей задержке и в
4.2 раза более лаконичных ответах.