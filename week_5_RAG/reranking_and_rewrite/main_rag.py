"""Demo v3: rewrite + broad search + HARD relevance threshold + cross-encoder rerank +
structured answer (Ответ / Использованные цитаты / Источники). Verbose logging shows exactly
whether the threshold check passed and what shape the final model output took."""

import logging

from agent_v2 import ask_agent_v2, HARD_REFUSAL_ANSWER
from retrieval_v2 import SIMILARITY_THRESHOLD

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)

DEMO_QUESTIONS = [
    "What was written on the bottle Alice found?",
    "What color was the caterpillar sitting on the mushroom?",
    "What did the Knave of Hearts steal?",
    "What year did Harry Potter meet Alice?",  # not in the book -> must trigger "I don't know" mode
]


def demo(question: str, strategy: str = "structural") -> None:
    print("\n" + "=" * 90)
    print(f"ВОПРОС: {question}")
    print("=" * 90)

    result = ask_agent_v2(question, mode="advanced", strategy=strategy)

    print(
        f"\n[ПОРОГ РЕЛЕВАНТНОСТИ] max cosine = {result['max_score']:.4f} "
        f"(порог = {SIMILARITY_THRESHOLD}) -> {'ПРОЙДЕН' if result['threshold_passed'] else 'НЕ ПРОЙДЕН'}"
    )

    if result["hard_refusal"]:
        print("[РЕЖИМ 'НЕ ЗНАЮ'] DeepSeek API НЕ вызывался — контекст недостаточно релевантен вопросу.")
        assert result["answer"] == HARD_REFUSAL_ANSWER
    else:
        print(
            f"[RERANK] {result['initial_count']} чанков после broad search -> "
            f"{result['final_count']} оставлено ({result['dropped_count']} отсеяно кросс-энкодером)"
        )
        print("\n--- Структурированный ответ модели (Ответ / Использованные цитаты / Источники) ---")

    print(result["answer"])

    if result["sources"]:
        print("\n--- Метаданные источников (для проверки, что цитаты не выдуманы) ---")
        for s in result["sources"]:
            print(
                f"  chunk_id={s['chunk_id']} | source={s['meta_source']} | section={s['meta_section']} "
                f"| cosine={s['score']:.4f} | rerank={s.get('rerank_score')}"
            )


def main() -> None:
    print("=== RAG v3: структурированный ответ + жёсткий порог релевантности + режим 'Не знаю' ===\n")

    for q in DEMO_QUESTIONS:
        demo(q)

    print("\n" + "=" * 90)
    print("Интерактивный режим. Для выхода: exit / quit")
    print("=" * 90)

    while True:
        try:
            question = input("\nВаш вопрос: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nЗавершение.")
            break

        if not question:
            continue
        if question.lower() in ("exit", "quit"):
            break

        demo(question)


if __name__ == "__main__":
    main()
