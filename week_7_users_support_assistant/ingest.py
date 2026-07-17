"""Индексация документации продукта в SQLite-хранилище векторов.

Конвейер: doc_loader.load_chunks -> эмбеддинг каждого чанка через Ollama `nomic-embed-text`
(префикс `search_document:` — документная сторона; в rag.py запрос идёт с `search_query:`) ->
запись в таблицу продукта.

Переиспользует `database` (схема + сохранение) и `embedder.get_embedding` (вызов Ollama) из
week_5_RAG; здесь добавлены только префикс задачи и создание таблицы.
"""

import json
import logging

import _bootstrap  # noqa: F401 — настраивает sys.path на модули week_5

from database import get_connection, save_chunks, CREATE_TABLE
from embedder import get_embedding

from config import SupportConfig
from doc_loader import load_chunks

logger = logging.getLogger(__name__)

# nomic-embed-text асимметричен: документы и запросы должны иметь разные префиксы.
DOC_PREFIX = "search_document: "


def embed_document(text: str) -> list[float] | None:
    """Эмбеддинг чанка корпуса с документным префиксом."""
    return get_embedding(DOC_PREFIX + text)


def _ensure_table(conn, table: str) -> None:
    conn.execute(CREATE_TABLE.format(table=table))
    conn.commit()


def ingest_product(cfg: SupportConfig) -> int:
    """Загружает, эмбеддит и сохраняет все чанки документации. Возвращает число чанков.

    RuntimeError, если Ollama не выдал ни одного эмбеддинга (чтобы пустой индекс не уехал
    незамеченным); единичная неудача терпима и логируется.
    """
    chunks = load_chunks(cfg)
    if not chunks:
        raise RuntimeError(
            f"Не найдено ни одного чанка документации '{cfg.product_name}' в {cfg.product_dir}. "
            f"Проверьте путь и glob-паттерны {cfg.doc_globs}."
        )

    logger.info("[INGEST] embedding %d chunks via nomic-embed-text ...", len(chunks))
    embedded = 0
    for i, chunk in enumerate(chunks, 1):
        vec = embed_document(chunk["text"])
        chunk["embedding"] = json.dumps(vec)
        if vec is not None:
            embedded += 1
        if i % 10 == 0 or i == len(chunks):
            logger.info("[INGEST] %d/%d embedded (%d ok)", i, len(chunks), embedded)

    if embedded == 0:
        raise RuntimeError(
            "Все эмбеддинги пустые — запущен ли Ollama и скачан ли `nomic-embed-text`? "
            "`sudo snap start ollama` (или `ollama serve`), затем `ollama pull nomic-embed-text`."
        )

    conn = get_connection(cfg.db_path)
    try:
        _ensure_table(conn, cfg.table)
        # Индекс пересобирается целиком: удалённые/переименованные разделы не должны оставаться.
        conn.execute(f"DELETE FROM {cfg.table}")
        conn.commit()
        save_chunks(conn, chunks, cfg.table)
    finally:
        conn.close()

    logger.info("[INGEST] stored %d chunks (%d embedded) -> %s [%s]",
                len(chunks), embedded, cfg.db_path, cfg.table)
    return len(chunks)
