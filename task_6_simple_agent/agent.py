import os
import json
from openai import OpenAI
import tiktoken


class DeepSeekAgent:
    """
    Агент для взаимодействия c DeepSeek API через OpenAI клиент.
    Управляет историей диалога с автоматическим сжатием старых сообщений.
    История автоматически сохраняется на диск.
    """

    def __init__(self, system_prompt: str = None, history_file: str = "chat_history.json", window_size: int = 4):
        """
        Инициализирует агента c API ключом из переменной окружения.

        Args:
            system_prompt: Системный промпт для модели (роль ассистента)
            history_file: Путь к файлу для сохранения истории диалогов
            window_size: Размер скользящего окна для хранения последних сообщений

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
        self.window_size = window_size
        self.default_system_prompt = (
            system_prompt or
            "Ты полезный помощник. Отвечай кратко и по существу на русском языке."
        )

        # Инициализируем скользящее окно и саммари
        self.messages_window = []
        self.history_summary = ""
        self._load_history()

        # Энкодер для подсчета токенов
        self.encoding = tiktoken.get_encoding("cl100k_base")

    def _load_history(self) -> None:
        """Загружает историю диалога из файла, если он существует."""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.messages_window = data.get("messages_window", [])
                        self.history_summary = data.get("history_summary", "")
                    else:
                        self.messages_window = data
                        self.history_summary = ""
                    self.history_loaded = True
            else:
                self.messages_window = []
                self.history_summary = ""
                self.history_loaded = False
        except (json.JSONDecodeError, IOError) as e:
            print(f"Предупреждение: Не удалось загрузить историю ({e}). Начинаем с пустой истории.")
            self.messages_window = []
            self.history_summary = ""
            self.history_loaded = False

    def _save_history(self) -> None:
        """Сохраняет текущую историю диалога в файл."""
        try:
            data = {
                "messages_window": self.messages_window,
                "history_summary": self.history_summary
            }
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
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

    def _create_summary(self, messages_to_summarize: list) -> str:
        """
        Создает саммари старых сообщений через API DeepSeek.

        Args:
            messages_to_summarize: Список сообщений для сжатия

        Returns:
            Краткое содержание сообщений
        """
        if not messages_to_summarize:
            return ""

        # Формируем текст для саммаризации
        dialog_text = "\n".join([
            f"{msg['role'].upper()}: {msg['content']}"
            for msg in messages_to_summarize
        ])

        # Запрос к API для создания саммари
        summary_prompt = f"""Сделай краткое саммари следующего диалога (максимум 3-4 предложения), объединив его с уже существующей сводкой:

Текущая сводка: {self.history_summary if self.history_summary else '(пусто)'}

Диалог для сжатия:
{dialog_text}

Новое краткое содержание:"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": summary_prompt}]
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Ошибка при создании саммари ({e}). Используем старую сводку.")
            return self.history_summary

    def send_message(self, user_text: str) -> tuple:
        """
        Отправляет сообщение пользователя в DeepSeek API с автоматическим сжатием истории.

        Args:
            user_text: Текст сообщения от пользователя

        Returns:
            Tuple: (текст ответа, dict с метриками токенов и сжатия)
        """
        current_query_tokens = len(self.encoding.encode(user_text))

        # Проверяем, будет ли окно переполнено ПОСЛЕ добавления нового сообщения
        compression_happened = False
        if len(self.messages_window) >= self.window_size:
            # Окно полное, нужно сжать ВСЕ текущие сообщения ДО добавления нового
            messages_to_compress = self.messages_window[:]

            print(f"\n[Сжатие] Старые сообщения отправлены на суммаризацию ({len(messages_to_compress)} сообщений)...")
            # Создаем новую саммари (объединяя со старой)
            self.history_summary = self._create_summary(messages_to_compress)
            print(f"[Сжатие] Саммари обновлена. Размер сжатого контекста: {len(self.history_summary)} символов")

            # Очищаем окно
            self.messages_window = []
            compression_happened = True

        # Добавляем новое сообщение пользователя в окно
        self.messages_window.append({
            "role": "user",
            "content": user_text
        })

        # Формируем массив сообщений для отправки в API
        messages_for_api = []

        # Системный промпт
        messages_for_api.append({
            "role": "system",
            "content": self.default_system_prompt
        })

        # Добавляем саммари как системное сообщение (если не пусто)
        if self.history_summary:
            messages_for_api.append({
                "role": "system",
                "content": f"Краткое содержание предыдущей части беседы:\n{self.history_summary}"
            })

        # Добавляем все сообщения из окна
        messages_for_api.extend(self.messages_window)

        # Подсчитываем токены контекста перед отправкой
        context_tokens = self._count_tokens(messages_for_api)

        # Отправляем в API
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages_for_api
        )

        # Извлекаем ответ
        assistant_response = response.choices[0].message.content
        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens

        # Добавляем ответ в окно
        self.messages_window.append({
            "role": "assistant",
            "content": assistant_response
        })

        # Сохраняем историю на диск
        self._save_history()

        # Метрики использования токенов
        metrics = {
            "current_query_tokens": current_query_tokens,
            "context_tokens_before_response": context_tokens,
            "prompt_tokens_used": prompt_tokens,
            "completion_tokens_used": completion_tokens,
            "total_this_step": prompt_tokens + completion_tokens,
            "window_size": len(self.messages_window),
            "window_capacity": self.window_size,
            "compression_happened": compression_happened,
            "summary_length": len(self.history_summary)
        }

        return assistant_response, metrics
