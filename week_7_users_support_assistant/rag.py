"""Поиск по документации продукта.

Два этапа, той же формы, что в `week_5_RAG/reranking_and_rewrite` и `week_7_assistant/rag.py`:
  1. эмбеддинг запроса (префикс `search_query:`) -> косинус по всем чанкам -> широкий top_k_initial
  2. дешёвый порог по косинусу — отсекает пустой индекс и полный мусор
  3. cross-encoder дорезает выживших до top_k_final
  4. ЖЁСТКИЙ порог по rerank-скору: если лучший чанк не релевантен и по мнению cross-encoder'а,
     останавливаемся ДО вызова LLM — в поддержке выдуманный ответ дороже честного «этого нет в
     документации»

Почему решает именно rerank, а не косинус. На русском корпусе `nomic-embed-text` держит высокий
базовый уровень: «Какая погода в Москве?» даёт лучший косинус 0.74 против 0.85 у настоящего
попадания — на таком зазоре порог по косинусу либо пропускает мусор, либо режет живые вопросы.
Cross-encoder судит пару (запрос, чанк) напрямую и разделяет их начисто: 0.99 против 0.000.
Поэтому косинусный порог оставлен низким (грубый фильтр), а решение принимает rerank.

Переиспользует `retrieval.cosine_similarity` и `retrieval_v2.rerank_with_cross_encoder`; здесь
добавлены только загрузка таблицы продукта, префикс задачи на стороне запроса и порог по rerank.
"""

import logging

import _bootstrap  # noqa: F401 — настраивает sys.path на модули week_5

from database import get_connection, load_chunks as _load_chunks
from embedder import get_embedding
from retrieval import cosine_similarity
from retrieval_v2 import rerank_with_cross_encoder

from config import SupportConfig

logger = logging.getLogger(__name__)

QUERY_PREFIX = "search_query: "     # запросная сторона nomic-embed-text (пара к DOC_PREFIX)
TOP_K_INITIAL = 12
TOP_K_FINAL = 4
SIMILARITY_THRESHOLD = 0.50         # грубый фильтр: пустой индекс / совсем далёкий запрос
RERANK_THRESHOLD = 0.10             # решающий порог: ниже — отказ вместо ответа


def embed_query(text: str) -> list[float] | None:
    return get_embedding(QUERY_PREFIX + text)


def retrieve(
    cfg: SupportConfig,
    query_text: str,
    top_k_initial: int = TOP_K_INITIAL,
    top_k_final: int = TOP_K_FINAL,
    threshold: float = SIMILARITY_THRESHOLD,
    rerank_threshold: float = RERANK_THRESHOLD,
) -> dict:
    """Возвращает {kept, max_score, max_rerank, threshold_passed, initial_count, dropped_count}.

    `kept` — переранжированный top_k_final список чанков (пуст, если порог не пройден или индекс
    пуст). У каждого чанка: chunk_id, text, meta_file, meta_section, score, rerank_score.
    """
    empty = {"kept": [], "max_score": 0.0, "max_rerank": None, "threshold_passed": False,
             "initial_count": 0, "dropped_count": 0}

    qvec = embed_query(query_text)
    if qvec is None:
        logger.warning("[RAG] Ollama недоступен — запрос не сэмбеддить")
        return empty

    conn = get_connection(cfg.db_path)
    try:
        chunks = _load_chunks(conn, cfg.table)
    except Exception as exc:
        logger.warning("[RAG] не читается таблица '%s' из %s: %s — документация проиндексирована?",
                       cfg.table, cfg.db_path, exc)
        return empty
    finally:
        conn.close()

    scored = []
    for c in chunks:
        emb = c.get("embedding")
        if not emb:
            continue
        scored.append({
            "chunk_id": c["chunk_id"],
            "text": c["text"],
            "meta_file": c.get("meta_file", ""),
            "meta_section": c.get("meta_section", ""),
            "score": cosine_similarity(qvec, emb),
        })
    scored.sort(key=lambda r: r["score"], reverse=True)
    candidates = scored[:top_k_initial]

    max_score = candidates[0]["score"] if candidates else 0.0
    passed = bool(candidates) and max_score >= threshold
    logger.info("[RAG] best cosine %.4f vs threshold %.2f -> %s",
                max_score, threshold, "PASS" if passed else "FAIL")

    if not passed:
        return {"kept": [], "max_score": max_score, "max_rerank": None, "threshold_passed": False,
                "initial_count": len(candidates), "dropped_count": len(candidates)}

    rr = rerank_with_cross_encoder(query_text, candidates, top_k_final=top_k_final)
    kept = rr["kept"]

    # Решающий порог. rerank_score отсутствует, если cross-encoder не загрузился (offline и т.п.):
    # тогда порог не применяем — конвейер продолжает работать на одном косинусе, как и в week_5.
    max_rerank = max((c["rerank_score"] for c in kept if c.get("rerank_score") is not None),
                     default=None)
    if max_rerank is not None and max_rerank < rerank_threshold:
        logger.info("[RAG] best rerank %.4f < %.2f -> нерелевантно, отказ до вызова LLM",
                    max_rerank, rerank_threshold)
        return {"kept": [], "max_score": max_score, "max_rerank": max_rerank,
                "threshold_passed": False, "initial_count": len(candidates),
                "dropped_count": len(candidates)}

    return {
        "kept": kept,
        "max_score": max_score,
        "max_rerank": max_rerank,
        "threshold_passed": True,
        "initial_count": len(candidates),
        "dropped_count": len(candidates) - len(kept),
    }
