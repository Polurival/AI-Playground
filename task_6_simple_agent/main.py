from agent import DeepSeekAgent


def main():
    """
    Главная функция, запускающая интерактивный чат с агентом.
    """
    try:
        agent = DeepSeekAgent()
        print("Агент инициализирован. Введите 'exit' или 'quit' для выхода.\n")

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
            response = agent.send_message(user_input)
            print(f"Агент: {response}\n")

    except ValueError as e:
        print(f"Ошибка: {e}")
    except KeyboardInterrupt:
        print("\nПрограмма прервана пользователем.")
    except Exception as e:
        print(f"Произошла ошибка: {e}")


if __name__ == "__main__":
    main()
