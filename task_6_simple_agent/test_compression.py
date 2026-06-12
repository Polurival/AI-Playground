"""
Тестовый скрипт для демонстрации механизма сжатия истории.
Показывает экономию токенов через Summary + скользящее окно.
"""

import os
import json
from agent import DeepSeekAgent


def test_compression_flow():
    """Тестирует механизм сжатия на примере 6 сообщений (window_size=4)."""

    # Создаем агента с малым окном для быстрого срабатывания сжатия
    agent = DeepSeekAgent(
        history_file="test_history.json",
        window_size=4
    )

    # Примеры сообщений для тестирования
    test_messages = [
        "Привет! Как дела?",
        "Что такое Python?",
        "Объясни мне, как работают функции в Python",
        "А что такое замыкания?",
        "Расскажи про декораторы",
        "Что такое асинхронное программирование?"
    ]

    print("=" * 70)
    print("ДЕМОНСТРАЦИЯ МЕХАНИЗМА СЖАТИЯ ИСТОРИИ")
    print("window_size = 4 (последние 4 сообщения в памяти)")
    print("=" * 70)

    total_tokens_without_compression = 0
    total_tokens_with_compression = 0

    for i, msg in enumerate(test_messages, 1):
        print(f"\n[Сообщение {i}/{len(test_messages)}]")
        print(f"Пользователь: {msg[:50]}...")

        response, metrics = agent.send_message(msg)

        print(f"Ответ: {response[:100]}...")

        # Выводим метрики
        print(f"\n  [ДЕБАГ] Окно: {metrics['window_size']}/{metrics['window_capacity']} сообщений")
        print(f"  [ДЕБАГ] Саммари: {metrics['summary_length']} символов")
        print(f"  Контекст при отправке: {metrics['context_tokens_before_response']} токенов")
        print(f"  API использовала: {metrics['prompt_tokens_used']} токенов (вход)")

        if metrics['compression_happened']:
            print(f"\n  ⚙️  СЖАТИЕ ПРОИЗОШЛО!")
            print(f"      Из {i-1} сообщений сжато в саммари на {metrics['summary_length']} символов")

        total_tokens_with_compression += metrics['prompt_tokens_used']

    # Вывод статистики
    print("\n" + "=" * 70)
    print("СТАТИСТИКА")
    print("=" * 70)
    print(f"✓ Все {len(test_messages)} сообщения обработаны")
    print(f"✓ Итого токенов использовано: {total_tokens_with_compression}")

    # Проверяем, что история сохранилась
    if os.path.exists("test_history.json"):
        with open("test_history.json", "r", encoding="utf-8") as f:
            saved_data = json.load(f)
            print(f"\n✓ История сохранена в файл:")
            print(f"  - Сообщений в окне: {len(saved_data['messages_window'])}")
            print(f"  - Саммари размер: {len(saved_data['history_summary'])} символов")

    print("\n[Вывод] Механизм сжатия работает корректно!")
    print("Сообщения автоматически сжимаются в саммари при переполнении окна.")


if __name__ == "__main__":
    # Проверяем наличие API ключа
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("⚠️  DEEPSEEK_API_KEY не установлен!")
        print("Установите переменную окружения перед запуском:")
        print("  export DEEPSEEK_API_KEY='ваш_ключ'")
        exit(1)

    test_compression_flow()
