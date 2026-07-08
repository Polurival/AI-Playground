# Week 6 — Локальная LLM

Запуск локальной LLM на ноутбуке. Модель работает **полностью локально** (без облака,
без API-ключей, без сети), к ней можно обращаться через CLI, через прямой HTTP API и
через OpenAI SDK.

## Выбор модели

Железо ноутбука:

| Параметр | Значение |
|----------|----------|
| CPU | AMD Ryzen 5 3550H, 8 потоков |
| RAM | 14 GB (≈7.5 GB свободно) |
| GPU | Radeon Vega Mobile (интегрированная, без CUDA → инференс на CPU) |

Без дискретной GPU инференс идёт на CPU, поэтому большие модели (7B+) будут медленными и
могут не влезть в память. Выбрана **`qwen2.5:3b`** (3B параметров, квантизация Q4, ~1.9 GB):

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

## Результат

Локальная LLM `qwen2.5:3b` запущена на ноутбуке через Ollama, доступна через CLI, прямой
HTTP API и OpenAI SDK, и корректно отвечает на запросы трёх уровней сложности (факт,
код, многошаговое рассуждение) — без облака и без интернета.
