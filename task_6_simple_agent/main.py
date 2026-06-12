from agent import DeepSeekAgent


def print_metrics(metrics: dict) -> None:
    """Выводит аккуратную статистику использования токенов и сжатия."""
    print("\n[ДЕБАГ] Состояние памяти:")
    print(f"  - Сообщений в окне: {metrics['window_size']}/{metrics['window_capacity']}")
    print(f"  - Саммари в памяти: {metrics['summary_length']} символов" + (" (пусто)" if metrics['summary_length'] == 0 else ""))

    print("\n[Аналитика токенов]")
    print(f"  - Текущий запрос пользователя: {metrics['current_query_tokens']} токенов")
    print(f"  - Контекст при отправке (с саммари): {metrics['context_tokens_before_response']} токенов")
    print(f"  - Ответ модели: {metrics['completion_tokens_used']} токенов")
    print(f"  - Итого за этот шаг (Вход + Выход): {metrics['total_this_step']} токенов")

    if metrics['compression_happened']:
        print("\n[✓] Сжатие выполнено на этом шаге")
    print()


def main():
    """
    Главная функция, запускающая интерактивный чат с агентом.
    """
    try:
        agent = DeepSeekAgent()

        # Вывести статус истории диалога
        if agent.history_loaded:
            print("✓ Обнаружена история прошлых диалогов. Контекст восстановлен.")
            print(f"  - Сообщений в окне: {len(agent.messages_window)}")
            print(f"  - Саммари предыдущей беседы: {len(agent.history_summary)} символов")
            print()
        else:
            print("✓ Предыдущая история не найдена. Начат новый диалог.\n")

        print("Агент инициализирован (window_size={0}). Введите 'exit' или 'quit' для выхода.\n".format(agent.window_size))

        while True:
            user_input = input("Вы: ").strip()

            # Обработка команд выхода
            if user_input.lower() in ["exit", "quit"]:
                print("До свидания!")
                break

            # Пропускаем пустые сообщения
            if not user_input:
                continue

            # Получаем ответ от агента
            response, metrics = agent.send_message(user_input)
            print(f"Агент: {response}")
            print_metrics(metrics)

    except KeyboardInterrupt:
        print("\nПрограмма прервана пользователем.")
    except Exception as e:
        print(f"Произошла ошибка: {e}")


if __name__ == "__main__":
    main()
