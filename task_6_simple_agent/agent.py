import os
import json
from openai import OpenAI
import tiktoken


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
        self.model = "deepseek-v4-flash"
        self.history_file = history_file
        self.history_loaded = False
        self.default_system_prompt = (
            system_prompt or
            "Ты полезный помощник. Отвечай кратко и по существу на русском языке."
        )

        # Инициализируем историю
        self.history = []
        self._load_history()

        # Энкодер для подсчета токенов
        self.encoding = tiktoken.get_encoding("cl100k_base")

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

    def _count_tokens(self, messages: list) -> int:
        """Подсчитывает токены в списке сообщений."""
        total_tokens = 0
        for msg in messages:
            content = msg.get("content", "")
            tokens = len(self.encoding.encode(content))
            total_tokens += tokens
        return total_tokens

    def send_message(self, user_text: str) -> tuple:
        """
        Отправляет сообщение пользователя в DeepSeek API.

        Args:
            user_text: Текст сообщения от пользователя

        Returns:
            Tuple: (текст ответа, dict с метриками токенов)
        """
        # Подсчитываем токены текущего запроса (до добавления в историю)
        current_query_tokens = len(self.encoding.encode(user_text))

        # Добавляем сообщение пользователя в историю
        self.history.append({
            "role": "user",
            "content": user_text
        })

        # Подсчитываем токены всей истории
        history_tokens = self._count_tokens(self.history)

        # Отправляем всю историю в API
        response = self.client.chat.completions.create(
            model=self.model,
            messages=self.history
        )

        # Извлекаем текст ответа и реальное использование токенов из API
        assistant_response = response.choices[0].message.content
        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens

        # Добавляем ответ ассистента в историю
        self.history.append({
            "role": "assistant",
            "content": assistant_response
        })

        # Сохраняем историю на диск
        self._save_history()

        # Возвращаем ответ и метрики использования токенов
        metrics = {
            "current_query_tokens": current_query_tokens,
            "history_tokens_before_response": history_tokens,
            "prompt_tokens_used": prompt_tokens,
            "completion_tokens_used": completion_tokens,
            "total_this_step": prompt_tokens + completion_tokens
        }

        return assistant_response, metrics
