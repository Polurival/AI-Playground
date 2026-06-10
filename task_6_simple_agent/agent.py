import os
import json
from openai import OpenAI


class DeepSeekAgent:
    """
    Агент для взаимодействия c DeepSeek API через OpenAI клиент.
    Управляет историей диалога и отправляет запросы c полным контекстом.
    История автоматически сохраняется на диск.
    """

    def __init__(self, system_prompt: str = None, history_file: str = "chat_history.json"):
        """
        Инициализирует агента c API ключом из переменной окружения.

        Args:
            system_prompt: Системный промпт для модели (роль ассистента)
            history_file: Путь к файлу для сохранения истории диалогов

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
        self.history_file = history_file
        self.history_loaded = False
        self.default_system_prompt = (
            system_prompt or
            "Ты полезный помощник. Отвечай кратко и по существу на русском языке."
        )

        # Инициализируем историю
        self.history = []
        self._load_history()

    def _load_history(self) -> None:
        """Загружает историю диалога из файла, если он существует."""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, "r", encoding="utf-8") as f:
                    self.history = json.load(f)
                    self.history_loaded = True
            else:
                # Инициализируем новую историю с системным промптом
                self.history = []
                self.history.append({
                    "role": "system",
                    "content": self.default_system_prompt
                })
                self.history_loaded = False
        except (json.JSONDecodeError, IOError) as e:
            print(f"Предупреждение: Не удалось загрузить историю ({e}). Начинаем с пустой истории.")
            self.history = []
            self.history.append({
                "role": "system",
                "content": self.default_system_prompt
            })
            self.history_loaded = False

    def _save_history(self) -> None:
        """Сохраняет текущую историю диалога в файл."""
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"Ошибка: Не удалось сохранить историю ({e}). Данные могут быть потеряны.")

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

        # Сохраняем историю на диск
        self._save_history()

        return assistant_response
