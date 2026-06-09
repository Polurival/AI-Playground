import os
from openai import OpenAI


class DeepSeekAgent:
    """
    Агент для взаимодействия c DeepSeek API через OpenAI клиент.
    Управляет историей диалога и отправляет запросы c полным контекстом.
    """

    def __init__(self, system_prompt: str = None):
        """
        Инициализирует агента c API ключом из переменной окружения.

        Args:
            system_prompt: Системный промпт для модели (роль ассистента)

        Raises:
            ValueError: Если переменная окружения DEEPSEEK_API_KEY не установлена
        """
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError(
                "Переменная окружения DEEPSEEK_API_KEY не установлена. "
                "Установите её перед запуском скрипта."
            )

        self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        self.model = "deepseek-chat"

        # Инициализируем историю с системным промптом
        self.history = []
        default_system_prompt = (
            system_prompt or
            "Ты полезный помощник. Отвечай кратко и по существу на русском языке."
        )
        self.history.append({
            "role": "system",
            "content": default_system_prompt
        })

    def send_message(self, user_text: str) -> str:
        """
        Отправляет сообщение пользователя в DeepSeek API.

        Args:
            user_text: Текст сообщения от пользователя

        Returns:
            Текст ответа от ассистента
        """
        # Добавляем сообщение пользователя в историю
        self.history.append({
            "role": "user",
            "content": user_text
        })

        # Отправляем всю историю в API
        response = self.client.chat.completions.create(
            model=self.model,
            messages=self.history
        )

        # Извлекаем текст ответа
        assistant_response = response.choices[0].message.content

        # Добавляем ответ ассистента в историю
        self.history.append({
            "role": "assistant",
            "content": assistant_response
        })

        return assistant_response
