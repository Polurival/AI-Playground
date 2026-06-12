"""
Демонстрация подсчета токенов в диалоге.
Показывает рост использования токенов с каждым сообщением.
"""

from agent import DeepSeekAgent
import os


def demo():
    """Демонстрирует подсчет и вывод токенов при диалоге."""

    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("❌ Ошибка: Не установлена DEEPSEEK_API_KEY")
        print("export DEEPSEEK_API_KEY='your-key-here'")
        return

    print("=" * 70)
    print("ДЕМОНСТРАЦИЯ: Подсчет токенов в диалоге")
    print("=" * 70)
    print()

    agent = DeepSeekAgent(
        system_prompt="Ты помощник. Отвечай кратко на русском языке."
    )

    messages = [
        "Привет! Что ты можешь делать?",
        "Какой сегодня день недели?",
        "Расскажи о себе кратко.",
        "Напиши текст про искусственный интеллект.",
    ]

    for i, msg in enumerate(messages, 1):
        msg_display = msg[:80] + "..." if len(msg) > 80 else msg
        print(f"📝 Сообщение {i}: '{msg_display}'")
        print("-" * 70)

        response, metrics = agent.send_message(msg)

        resp_display = response[:150] + "..." if len(response) > 150 else response
        print(f"✓ Ответ: {resp_display}\n")

        print("[Метрики этого шага]")
        print(f"  • Текущий запрос: {metrics['current_query_tokens']} токенов")
        print(f"  • Контекст до ответа: {metrics['history_tokens_before_response']} токенов")
        print(f"  • Ответ модели: {metrics['completion_tokens_used']} токенов")
        print(f"  • Всего за шаг: {metrics['total_this_step']} токенов")

        print()
        print("=" * 70)
        print()


if __name__ == "__main__":
    demo()
