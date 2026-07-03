"""Demo: ask the same question with and without RAG, side by side."""

import logging

from agent import ask_agent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)

DEMO_QUESTIONS = [
    "What was written on the bottle Alice found?",
    "What color was the caterpillar sitting on the mushroom?",
    "What did the Knave of Hearts steal?",
]


def demo(question: str, strategy: str = "structural") -> None:
    print("\n" + "=" * 80)
    print(f"ВОПРОС: {question}")
    print("=" * 80)

    print("\n--- Режим БЕЗ RAG ---")
    result = ask_agent(question, use_rag=False)
    print(result["answer"])

    print(f"\n--- Режим С RAG (strategy={strategy}) ---")
    result = ask_agent(question, use_rag=True, strategy=strategy)
    print(result["answer"])
    print("\nИспользованные источники:")
    for s in result["sources"]:
        print(f"  [{s['score']:.4f}] {s['chunk_id']} — {s['meta_section']}")


def main() -> None:
    print("=== RAG-агент по книге 'Алиса в Стране чудес' ===")
    print("Демонстрация: одни и те же вопросы в режимах БЕЗ RAG и С RAG.\n")

    for q in DEMO_QUESTIONS:
        demo(q)

    print("\n" + "=" * 80)
    print("Интерактивный режим. Для выхода: exit / quit")
    print("=" * 80)

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
