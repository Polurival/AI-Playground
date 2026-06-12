from agent import DeepSeekAgent


def print_metrics(metrics: dict) -> None:
    """Выводит аккуратную статистику использования токенов."""
    print("\n[Аналитика токенов]")
    print(f"  - Текущий запрос пользователя: {metrics['current_query_tokens']} токенов")
    print(f"  - Всего в истории (контекст отправки): {metrics['history_tokens_before_response']} токенов")
    print(f"  - Ответ модели: {metrics['completion_tokens_used']} токенов")
    print(f"  - Итого за этот шаг (Вход + Выход): {metrics['total_this_step']} токенов")
    print()


def print_status(agent: DeepSeekAgent) -> None:
    """Выводит статус использования контекстного лимита."""
    status = agent.get_status()
    used = status['used']
    limit = status['limit']
    percent = status['percent']
    msg_count = status['messages_count']

    print(f"\n[Статус контекста]")
    print(f"  - Использовано токенов: {used} / {limit} ({percent:.1f}%)")
    print(f"  - Сообщений в истории: {msg_count}")

    if percent > 80:
        print(f"  ⚠ ВНИМАНИЕ: Контекст заполнен на {percent:.0f}%!")
    print()


def main():
    """
    Главная функция, запускающая интерактивный чат с агентом.
    """
    try:
        agent = DeepSeekAgent()

        # Вывести статус истории диалога
        if agent.history_loaded:
            print("✓ Обнаружена история прошлых диалогов. Контекст восстановлен.\n")
        else:
            print("✓ Предыдущая история не найдена. Начат новый диалог.\n")

        print("Агент инициализирован.")
        print("Команды: 'exit'/'quit' для выхода, '/status' для показа использования контекста.\n")

        while True:
            user_input = input("Вы: ").strip()

            # Обработка команд выхода
            if user_input.lower() in ["exit", "quit"]:
                print("До свидания!")
                break

            # Обработка команды статуса
            if user_input.lower() == "/status":
                print_status(agent)
                continue

            # Пропускаем пустые сообщения
            if not user_input:
                continue

            # Получаем ответ от агента
            try:
                response, metrics = agent.send_message(user_input)
                print(f"Агент: {response}")
                print_metrics(metrics)
            except ValueError as e:
                print(f"⚠ {e}\n")

    except KeyboardInterrupt:
        print("\nПрограмма прервана пользователем.")
    except Exception as e:
        print(f"Произошла ошибка: {e}")


if __name__ == "__main__":
    main()
