#!/usr/bin/env python3

#######################################
# Сравнение слабой, средней и сильной модели через HuggingFace Inference API
# (без локальной GPU — только облачный inference).
#
# Установка:
#   python3 -m venv hf-env
#   source hf-env/bin/activate
#   pip install huggingface_hub
#
# Токен (fine-grained, permission: "Make calls to Inference Providers"):
#   https://huggingface.co/settings/tokens
#   export HF_TOKEN='hf_...'
#
# Примеры запуска:
#   python3 task_5_benchmark_hf.py
#   python3 task_5_benchmark_hf.py "Что такое Python? Ответь в 3 предложениях."
#   python3 task_5_benchmark_hf.py --logic-task
#   python3 task_5_benchmark_hf.py --logic-task --max-tokens 800 --temperature 0.3
#   python3 task_5_benchmark_hf.py --show-answers
#   python3 task_5_benchmark_hf.py --check-models
#   python3 task_5_benchmark_hf.py \
#       --weak-model meta-llama/Llama-3.2-1B-Instruct \
#       --medium-model meta-llama/Llama-3.2-3B-Instruct \
#       --strong-model meta-llama/Meta-Llama-3-8B-Instruct
#
# Если model_not_supported — включите провайдеры:
#   https://huggingface.co/settings/inference-providers
# Для Llama/Gemma может понадобиться принять лицензию на странице модели.
#######################################

import argparse
import os
import sys
import time
from dataclasses import dataclass

from huggingface_hub import HfApi, InferenceClient
from huggingface_hub.errors import HfHubHTTPError

LOGIC_TASK = """
На острове живут рыцари и лжецы.

Рыцари всегда говорят правду.
Лжецы всегда лгут.

Вы встретили трех жителей: A, B и C.

A говорит:

«B — лжец».

B говорит:

«C — лжец».

C говорит:

«A и B одного типа».

Определите, кто является рыцарем, а кто лжецом.

В самом конце ответа обязательно добавь отдельный блок:

ФИНАЛЬНЫЙ ОТВЕТ:
A — рыцарь/лжец
B — рыцарь/лжец
C — рыцарь/лжец
""".strip()

DEFAULT_QUESTION = (
    "Что такое Python? Ответь кратко: 3–4 предложения, без списков."
)

# Модели — выбраны для совместимости с провайдерами together, featherless-ai, novita.
# Если какая-то модель недоступна, используйте флаги:
#   python3 task_5_benchmark_hf.py --weak-model <model_id> --medium-model <model_id> --strong-model <model_id>
DEFAULT_MODELS = {
    "weak": "meta-llama/Llama-3.1-8B-Instruct",
    "medium": "meta-llama/Llama-3.1-70B-Instruct",
    "strong": "meta-llama/Meta-Llama-3-8B-Instruct",
}

# Ориентировочные цены провайдеров HF (USD за 1M токенов, cache miss).
# Точная сумма зависит от выбранного провайдера — см. HF billing dashboard.
ESTIMATED_PRICES_USD_PER_1M = {
    "TinyLlama/TinyLlama-1.1B-Chat-v1.0": {"input": 0.02, "output": 0.06},
    "meta-llama/Llama-2-7B-chat": {"input": 0.07, "output": 0.14},
    "meta-llama/Meta-Llama-3-8B-Instruct": {"input": 0.20, "output": 0.40},
}

MAX_RETRIES = 3
RETRY_BACKOFF_S = 5


@dataclass
class BenchmarkResult:
    tier: str
    model: str
    elapsed_s: float
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    estimated_cost_usd: float | None
    answer: str
    error: str | None = None


def get_chat_providers(model: str, token: str) -> list[str]:
    """Провайдеры HF, у которых модель поддерживает chat (conversational)."""
    try:
        info = HfApi(token=token).model_info(
            model, expand=["inferenceProviderMapping"]
        )
    except Exception:
        return []

    providers = []
    mapping = getattr(info, "inference_provider_mapping", None) or []
    for entry in mapping:
        task = getattr(entry, "task", None)
        provider = getattr(entry, "provider", None)
        if task in ("conversational", "chat") and provider:
            providers.append(provider)
    return providers


def print_model_availability(models: dict[str, str], token: str) -> None:
    print("\nПроверка доступности моделей (chat):")
    any_ok = False
    for tier, model in models.items():
        providers = get_chat_providers(model, token)
        if providers:
            any_ok = True
            print(f"  {tier}: {model}")
            print(f"    провайдеры: {', '.join(providers)}")
        else:
            print(f"  {tier}: {model}")
            print("    провайдеры: нет (model_not_supported)")
    if not any_ok:
        print(
            "\nНи одна модель недоступна. Что сделать:\n"
            "  1. Включите провайдеры: https://huggingface.co/settings/inference-providers\n"
            "  2. Примите лицензию модели на её странице на HuggingFace\n"
            "  3. Подберите модели с фильтром «Inference available»:\n"
            "     https://huggingface.co/models?pipeline_tag=text-generation&inference=warm\n"
            "  4. Запустите с --check-models и укажите рабочие ID через --weak-model и т.д."
        )


def format_error_hint(error: str) -> str | None:
    lower = error.lower()
    if "model_not_supported" in lower or "not supported by any provider" in lower:
        return (
            "Модель недоступна у включённых провайдеров. "
            "См. https://huggingface.co/settings/inference-providers"
        )
    if "503" in error or "temporarily unavailable" in lower:
        return "Временная перегрузка сервиса — повторите позже или смените модель."
    if "401" in error or "403" in error or "unauthorized" in lower:
        return "Проверьте HF_TOKEN и permission «Make calls to Inference Providers»."
    return None


def get_hf_token() -> str:
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if not token:
        print("Error: set HF_TOKEN (or HUGGING_FACE_HUB_TOKEN) environment variable")
        print("Create token: https://huggingface.co/settings/tokens")
        print("Required permission: Make calls to Inference Providers")
        print("Run: export HF_TOKEN='hf_...'")
        sys.exit(1)
    return token


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float | None:
    prices = ESTIMATED_PRICES_USD_PER_1M.get(model)
    if not prices:
        return None
    return (
        prompt_tokens * prices["input"] + completion_tokens * prices["output"]
    ) / 1_000_000


def extract_usage(response) -> tuple[int | None, int | None, int | None]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None, None, None

    prompt_tokens = getattr(usage, "prompt_tokens", None)
    completion_tokens = getattr(usage, "completion_tokens", None)
    total_tokens = getattr(usage, "total_tokens", None)

    if isinstance(usage, dict):
        prompt_tokens = usage.get("prompt_tokens", prompt_tokens)
        completion_tokens = usage.get("completion_tokens", completion_tokens)
        total_tokens = usage.get("total_tokens", total_tokens)

    return prompt_tokens, completion_tokens, total_tokens


def run_benchmark(
    client: InferenceClient,
    *,
    tier: str,
    model: str,
    question: str,
    max_tokens: int,
    temperature: float,
) -> BenchmarkResult:
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": question},
    ]

    start = time.perf_counter()
    last_error: str | None = None
    response = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            last_error = None
            break
        except HfHubHTTPError as exc:
            last_error = str(exc)
            if "503" in last_error and attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF_S * attempt
                print(f"    503, повтор {attempt}/{MAX_RETRIES} через {wait} с...", flush=True)
                time.sleep(wait)
                continue
            break
        except Exception as exc:  # noqa: BLE001 — show any provider error in benchmark table
            last_error = f"{type(exc).__name__}: {exc}"
            if "503" in last_error and attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF_S * attempt
                print(f"    503, повтор {attempt}/{MAX_RETRIES} через {wait} с...", flush=True)
                time.sleep(wait)
                continue
            break

    elapsed = time.perf_counter() - start
    if last_error is not None or response is None:
        return BenchmarkResult(
            tier=tier,
            model=model,
            elapsed_s=elapsed,
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
            estimated_cost_usd=None,
            answer="",
            error=last_error or "unknown error",
        )

    choice = response.choices[0]
    answer = (choice.message.content or "").strip()
    prompt_tokens, completion_tokens, total_tokens = extract_usage(response)

    estimated_cost = None
    if prompt_tokens is not None and completion_tokens is not None:
        estimated_cost = estimate_cost_usd(model, prompt_tokens, completion_tokens)

    return BenchmarkResult(
        tier=tier,
        model=model,
        elapsed_s=elapsed,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=estimated_cost,
        answer=answer,
    )


def format_tokens(result: BenchmarkResult) -> str:
    if result.error:
        return "—"
    parts = []
    if result.prompt_tokens is not None:
        parts.append(f"in={result.prompt_tokens}")
    if result.completion_tokens is not None:
        parts.append(f"out={result.completion_tokens}")
    if result.total_tokens is not None:
        parts.append(f"Σ={result.total_tokens}")
    return ", ".join(parts) if parts else "n/a"


def format_cost(result: BenchmarkResult) -> str:
    if result.error:
        return "—"
    if result.estimated_cost_usd is None:
        return "n/a"
    return f"${result.estimated_cost_usd:.6f}"


def print_summary_table(results: list[BenchmarkResult]) -> None:
    headers = ("Уровень", "Модель", "Время, с", "Токены", "Стоимость*", "Статус")
    rows = []
    for r in results:
        status = "OK" if not r.error else "ERROR"
        rows.append(
            (
                r.tier,
                r.model,
                f"{r.elapsed_s:.2f}",
                format_tokens(r),
                format_cost(r),
                status,
            )
        )

    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(cells: tuple[str, ...]) -> str:
        return " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

    separator = "-+-".join("-" * w for w in widths)

    print("\n" + "=" * len(separator))
    print("СВОДНАЯ ТАБЛИЦА")
    print("=" * len(separator))
    print(fmt_row(headers))
    print(separator)
    for row in rows:
        print(fmt_row(row))
    print("=" * len(separator))
    print(
        "* Стоимость — ориентировочная оценка по типичным тарифам провайдеров HF.\n"
        "  Точные списания: https://huggingface.co/settings/billing"
    )


def print_comparison_notes(results: list[BenchmarkResult]) -> None:
    ok = [r for r in results if not r.error]
    if len(ok) < 2:
        return

    fastest = min(ok, key=lambda r: r.elapsed_s)
    slowest = max(ok, key=lambda r: r.elapsed_s)

    print("\nСравнение:")
    print(f"  Скорость: быстрее всех — {fastest.tier} ({fastest.elapsed_s:.2f} с)")
    print(f"            медленнее всех — {slowest.tier} ({slowest.elapsed_s:.2f} с)")

    with_tokens = [r for r in ok if r.total_tokens is not None]
    if with_tokens:
        lightest = min(with_tokens, key=lambda r: r.total_tokens or 0)
        heaviest = max(with_tokens, key=lambda r: r.total_tokens or 0)
        print(
            f"  Ресурсоёмкость: меньше токенов — {lightest.tier} "
            f"({lightest.total_tokens}); больше — {heaviest.tier} ({heaviest.total_tokens})"
        )

    with_cost = [r for r in ok if r.estimated_cost_usd is not None]
    if with_cost:
        cheapest = min(with_cost, key=lambda r: r.estimated_cost_usd or 0)
        priciest = max(with_cost, key=lambda r: r.estimated_cost_usd or 0)
        print(
            f"  Стоимость (~): дешевле — {cheapest.tier} ({format_cost(cheapest)}); "
            f"дороже — {priciest.tier} ({format_cost(priciest)})"
        )

    print("  Качество: сравните полные ответы ниже (или запустите с --show-answers).")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Бенчмарк слабой/средней/сильной модели через HuggingFace Inference API"
    )
    parser.add_argument(
        "question",
        nargs="?",
        default=None,
        help="Один и тот же промпт для всех трёх моделей",
    )
    parser.add_argument(
        "--logic-task",
        action="store_true",
        help="Использовать логическую задачу (рыцари и лжецы) из task_3.py",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=500,
        help="Максимум токенов в ответе (default: 500)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.7,
        help="Temperature 0–1 (default: 0.7)",
    )
    parser.add_argument(
        "--weak-model",
        default=DEFAULT_MODELS["weak"],
        help=f"Слабая модель (default: {DEFAULT_MODELS['weak']})",
    )
    parser.add_argument(
        "--medium-model",
        default=DEFAULT_MODELS["medium"],
        help=f"Средняя модель (default: {DEFAULT_MODELS['medium']})",
    )
    parser.add_argument(
        "--strong-model",
        default=DEFAULT_MODELS["strong"],
        help=f"Сильная модель (default: {DEFAULT_MODELS['strong']})",
    )
    parser.add_argument(
        "--bill-to",
        default=None,
        help="Имя HF-организации для биллинга (опционально)",
    )
    parser.add_argument(
        "--show-answers",
        action="store_true",
        help="Печатать полные ответы всех моделей",
    )
    parser.add_argument(
        "--check-models",
        action="store_true",
        help="Только проверить доступность моделей у провайдеров и выйти",
    )
    args = parser.parse_args()

    if args.logic_task:
        question = LOGIC_TASK
    elif args.question:
        question = args.question
    else:
        question = DEFAULT_QUESTION

    models = {
        "слабая": args.weak_model,
        "средняя": args.medium_model,
        "сильная": args.strong_model,
    }

    token = get_hf_token()
    client_kwargs: dict = {"token": token}
    if args.bill_to:
        client_kwargs["bill_to"] = args.bill_to

    if args.check_models:
        print_model_availability(models, token)
        return

    client = InferenceClient(**client_kwargs)

    print("HuggingFace Inference API benchmark")
    print_model_availability(models, token)
    print(f"max_tokens={args.max_tokens}, temperature={args.temperature}")
    print("\nПромпт:\n" + "-" * 50)
    print(question)
    print("-" * 50)

    results: list[BenchmarkResult] = []
    for tier, model in models.items():
        print(f"\n>>> Запрос: {tier} ({model}) ...", flush=True)
        result = run_benchmark(
            client,
            tier=tier,
            model=model,
            question=question,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
        )
        results.append(result)

        if result.error:
            print(f"    Ошибка: {result.error}")
            hint = format_error_hint(result.error)
            if hint:
                print(f"    Подсказка: {hint}")
        else:
            preview = result.answer.replace("\n", " ")
            if len(preview) > 120:
                preview = preview[:117] + "..."
            print(f"    Время: {result.elapsed_s:.2f} с | Токены: {format_tokens(result)}")
            print(f"    Превью: {preview}")

    print_summary_table(results)
    print_comparison_notes(results)

    if all(r.error for r in results):
        print(
            "\nВсе запросы завершились с ошибкой. Быстрый чеклист:\n"
            "  • python3 task_5_benchmark_hf.py --check-models\n"
            "  • https://huggingface.co/settings/inference-providers — включить провайдеры\n"
            "  • Принять лицензию на страницах моделей (meta-llama, google/gemma, …)\n"
            "  • Подобрать модели: https://huggingface.co/models?inference=warm"
        )

    if args.show_answers:
        print("\n" + "=" * 50)
        print("ПОЛНЫЕ ОТВЕТЫ")
        print("=" * 50)
        for r in results:
            print(f"\n--- {r.tier}: {r.model} ---")
            if r.error:
                print(f"[ошибка] {r.error}")
            else:
                print(r.answer if r.answer else "(пустой ответ)")


if __name__ == "__main__":
    main()
