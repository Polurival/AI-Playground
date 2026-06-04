#!/usr/bin/env python3

#######################################
# Install venv if not already installed
# sudo apt install python3-venv
#
# python3 -m venv deepseek-env
# source deepseek-env/bin/activate
# pip install openai
#
# export DEEPSEEK_API_KEY='your-key-here'
#
# Способы решения (параметр method):
#   direct       — прямой ответ без дополнительных инструкций
#   step_by_step — с инструкцией «решай пошагово»
#   meta_prompt  — модель сначала составляет промпт, затем по нему решает
#   experts      — группа экспертов (аналитик, инженер, критик)
#
# Примеры запуска:
#   python3 task_3.py direct
#   python3 task_3.py step_by_step
#   python3 task_3.py meta_prompt
#   python3 task_3.py experts
#
#   python3 task_3.py direct --max-tokens 800 --temperature 0.3
#   python3 task_3.py step_by_step --max-tokens 2500 --temperature 0.5
#   python3 task_3.py meta_prompt --max-tokens 2500
#   python3 task_3.py experts --max-tokens 2500
#######################################

import argparse
import os
import sys

from openai import OpenAI

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
""".strip()

FINAL_ANSWER_INSTRUCTION = """
В самом конце ответа обязательно добавь отдельный блок:

ФИНАЛЬНЫЙ ОТВЕТ:
A — рыцарь/лжец
B — рыцарь/лжец
C — рыцарь/лжец
""".strip()

METHODS = ("direct", "step_by_step", "meta_prompt", "experts")

API_KEY = os.environ.get("DEEPSEEK_API_KEY")

if not API_KEY:
    print("Error: Please set DEEPSEEK_API_KEY environment variable")
    print("Run: export DEEPSEEK_API_KEY='your-key-here'")
    sys.exit(1)

parser = argparse.ArgumentParser(
    description="Решение логической задачи (рыцари и лжецы) через DeepSeek API"
)
parser.add_argument(
    "method",
    choices=METHODS,
    help="Способ решения: " + ", ".join(METHODS),
)
parser.add_argument(
    "--max-tokens",
    type=int,
    default=800,
    help="Maximum tokens in response (default: 800; для step_by_step/meta_prompt/experts минимум 2000)",
)
parser.add_argument(
    "--temperature",
    type=float,
    default=0.7,
    help="Creativity level 0-1 (default: 0.7)",
)
args = parser.parse_args()


def tokens_for_long_tasks() -> int:
    return max(args.max_tokens, 2000)


def create_client() -> OpenAI:
    return OpenAI(
        api_key=API_KEY,
        base_url="https://api.deepseek.com",
    )


def message_text(message) -> str:
    content = (message.content or "").strip()
    if content:
        return content

    reasoning = getattr(message, "reasoning_content", None)
    if isinstance(reasoning, str) and reasoning.strip():
        print(
            "[предупреждение: content пуст, показан reasoning_content]\n",
            file=sys.stderr,
        )
        return reasoning.strip()

    return ""


def print_final_block(text: str) -> None:
    print("\n" + "=" * 50)
    print("ФИНАЛЬНЫЙ ОТВЕТ")
    print("=" * 50)
    print(text.strip() if text.strip() else "(пустой ответ)")
    print("=" * 50)


def extract_final_answer(text: str) -> str | None:
    marker = "ФИНАЛЬНЫЙ ОТВЕТ"
    upper = text.upper()
    idx = upper.find(marker)
    if idx == -1:
        return None
    return text[idx:].strip()


def chat(
    client: OpenAI,
    user_content: str,
    system_content: str = "You are a helpful assistant.",
    *,
    label=None,
    max_tokens=None,
    thinking=True,
    reasoning_effort="high",
) -> str:
    if label:
        print(f"\n--- {label} ---\n")

    request_kwargs = {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ],
        "stream": False,
        "max_tokens": max_tokens if max_tokens is not None else args.max_tokens,
        "temperature": args.temperature,
    }
    if thinking:
        request_kwargs["reasoning_effort"] = reasoning_effort
        request_kwargs["extra_body"] = {"thinking": {"type": "enabled"}}

    response = client.chat.completions.create(**request_kwargs)
    choice = response.choices[0]
    text = message_text(choice.message)

    if choice.finish_reason == "length":
        print(
            "[предупреждение: ответ обрезан по max_tokens, увеличьте --max-tokens]\n",
            file=sys.stderr,
        )

    print(text)
    return text


def request_final_answer(client: OpenAI, context: str = "") -> str:
    context_block = f"\n\nКонтекст предыдущих рассуждений:\n{context}" if context else ""
    prompt = f"""{LOGIC_TASK}

Дай только краткий итог задачи в формате:

ФИНАЛЬНЫЙ ОТВЕТ:
A — рыцарь или лжец
B — рыцарь или лжец
C — рыцарь или лжец

Без длинных рассуждений.{context_block}"""

    return chat(
        client,
        prompt,
        system_content="Отвечай кратко. Обязательно используй блок «ФИНАЛЬНЫЙ ОТВЕТ:».",
        label="Итоговый ответ",
        max_tokens=300,
        thinking=False,
    )


def build_user_prompt(method: str) -> str:
    if method == "direct":
        return LOGIC_TASK

    if method == "step_by_step":
        return f"Решай пошагово.\n\n{LOGIC_TASK}"

    raise ValueError(f"Unknown method: {method}")


def solve_direct(client: OpenAI) -> None:
    chat(client, build_user_prompt("direct"), label="Способ 1: прямой ответ")


def solve_step_by_step(client: OpenAI) -> None:
    chat(
        client,
        build_user_prompt("step_by_step"),
        label="Способ 2: пошагово",
        max_tokens=tokens_for_long_tasks(),
        reasoning_effort="low",
    )


def solve_meta_prompt(client: OpenAI) -> None:
    meta_request = f"""Составь компактный промпт (до 400 слов) для языковой модели,
чтобы она корректно решила следующую логическую задачу.
Верни только текст промпта — без решения задачи.

Задача:
{LOGIC_TASK}"""

    generated_prompt = chat(
        client,
        meta_request,
        system_content="Ты помогаешь формулировать промпты для решения логических задач.",
        label="Способ 3, шаг 1: составление промпта",
        max_tokens=tokens_for_long_tasks(),
        reasoning_effort="low",
    )

    solve_request = f"""Используй следующий промпт для решения задачи.

--- ПРОМПТ ---
{generated_prompt}
--- КОНЕЦ ПРОМПТА ---

Задача:
{LOGIC_TASK}

{FINAL_ANSWER_INSTRUCTION}"""

    solution = chat(
        client,
        solve_request,
        label="Способ 3, шаг 2: решение по сгенерированному промпту",
        max_tokens=tokens_for_long_tasks(),
        reasoning_effort="low",
    )

    final = extract_final_answer(solution)
    if final:
        print_final_block(final)
    else:
        final = request_final_answer(client, context=solution)
        print_final_block(extract_final_answer(final) or final)


def solve_experts(client: OpenAI) -> None:
    expert_specs = [
        (
            "Эксперт: Аналитик",
            "Ты — аналитик. Формализуй утверждения A, B и C, перечисли варианты типов.",
            f"""{LOGIC_TASK}

Твоя роль: Аналитик.
Формализуй утверждения, предложи план перебора или таблицу истинности.
Не давай окончательный вердикт по всем троим — только анализ.""",
        ),
        (
            "Эксперт: Инженер",
            "Ты — инженер. Проверяй варианты на согласованность с репликами.",
            f"""{LOGIC_TASK}

Твоя роль: Инженер.
Проверь каждый вариант (A,B,C — рыцарь/лжец) на согласованность с репликами.
Укажи, какие варианты отпадают и почему.""",
        ),
        (
            "Эксперт: Критик",
            "Ты — критик. Ищи ошибки в логике и проверяй выводы.",
            f"""{LOGIC_TASK}

Твоя роль: Критик.
Проверь типичные ошибки в задачах о рыцарях и лжецах, укажи, что нужно перепроверить.""",
        ),
    ]

    expert_outputs = {}
    long_tokens = tokens_for_long_tasks()

    for label, system, user in expert_specs:
        text = chat(
            client,
            user,
            system_content=system,
            label=f"Способ 4 — {label}",
            max_tokens=long_tokens,
            reasoning_effort="low",
        )
        expert_outputs[label] = text

    context = "\n\n".join(
        f"### {name}\n{text}" for name, text in expert_outputs.items()
    )

    synthesis = chat(
        client,
        f"""{LOGIC_TASK}

Ниже мнения экспертов. Сопоставь их, найди согласованное решение.

{context}

{FINAL_ANSWER_INSTRUCTION}""",
        system_content="Ты координатор экспертной группы. Обязательно выведи блок «ФИНАЛЬНЫЙ ОТВЕТ:».",
        label="Способ 4 — координатор (сводка)",
        max_tokens=long_tokens,
        reasoning_effort="low",
    )

    final = extract_final_answer(synthesis)
    if final:
        print_final_block(final)
    else:
        final = request_final_answer(client, context=context + "\n\n" + synthesis)
        print_final_block(extract_final_answer(final) or final)


def main() -> None:
    print(f"Метод: {args.method}")
    print(f"max_tokens={args.max_tokens}, temperature={args.temperature}")
    if args.method in ("step_by_step", "meta_prompt", "experts") and args.max_tokens < 2000:
        print(
            f"Подсказка: для {args.method} используется минимум {tokens_for_long_tasks()} "
            "токенов на длинные шаги",
            file=sys.stderr,
        )
    print(f"\nЗадача:\n{LOGIC_TASK}\n")

    client = create_client()

    solvers = {
        "direct": solve_direct,
        "step_by_step": solve_step_by_step,
        "meta_prompt": solve_meta_prompt,
        "experts": solve_experts,
    }
    solvers[args.method](client)


if __name__ == "__main__":
    main()
