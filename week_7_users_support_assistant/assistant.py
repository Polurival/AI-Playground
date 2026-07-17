"""Мозг ассистента поддержки: ответ на вопрос пользователя, обоснованный документацией (RAG)
и данными CRM (MCP).

Поток:
  вопрос [+ ticket_id / user_id]
    -> контекст CRM через MCP (тикет + карточка автора: тариф, SSO/2FA, код ошибки)
    -> перезапись запроса С УЧЁТОМ фактов тикета (код ошибки и тариф попадают в поисковый запрос)
    -> RAG по документации продукта
    -> ЖЁСТКИЙ порог: если релевантного нет — отказ + эскалация, LLM не вызывается
    -> генерация ответа только по выдержкам + контексту клиента, со ссылками на файлы

Вызовы LLM идут через `llm_provider` из week_5, поэтому один и тот же код отвечает через
DeepSeek (облако) или локальную модель в Ollama — переключение `set_provider("local"|"deepseek")`.
"""

import logging

import _bootstrap  # noqa: F401 — настраивает sys.path на модули week_5

import llm_provider

from config import SupportConfig
from rag import retrieve
import crm_context

logger = logging.getLogger(__name__)

REWRITE_SYSTEM_PROMPT = (
    "Ты переписываешь вопрос пользователя службы поддержки в плотный поисковый запрос для "
    "семантического поиска по документации продукта.\n"
    "- Если дан контекст обращения, ОБЯЗАТЕЛЬНО перенеси в запрос код ошибки, раздел продукта и "
    "тариф клиента — это они определяют нужный раздел документации.\n"
    "- Сохраняй коды ошибок, названия разделов и технические термины ДОСЛОВНО.\n"
    "- Только ключевые существительные, без воды; одна строка; не отвечай на вопрос.\n"
    "- Отвечай на русском.\n"
    "- Выведи ТОЛЬКО запрос — без кавычек и пояснений."
)

ANSWER_SYSTEM_PROMPT = (
    "Ты — ассистент службы поддержки продукта {name}. Отвечай пользователю на русском языке, "
    "используя ТОЛЬКО выдержки из документации и контекст клиента из CRM, приведённые ниже.\n"
    "- Учитывай тариф клиента и его настройки: один и тот же симптом на разных тарифах имеет "
    "разные причины и разные решения. Если причина в ограничении тарифа — скажи об этом прямо и "
    "назови тариф клиента.\n"
    "- Если в обращении есть код ошибки — опирайся именно на него.\n"
    "- Обращайся к клиенту по имени, если оно известно; тон вежливый и деловой.\n"
    "- Давай конкретные шаги (пункты меню, команды), а не общие советы.\n"
    "- Каждое утверждение должно следовать из выдержек; в конце укажи использованные файлы "
    "документации, например (docs/auth_sso.md).\n"
    "- Если в материалах нет ответа — скажи это прямо и предложи эскалацию инженеру. Не выдумывай."
)


def _rewrite(question: str, crm_facts: dict) -> str:
    """Переписывает вопрос в поисковый запрос, подмешивая факты обращения из CRM."""
    facts_line = crm_context.facts_for_query(crm_facts)
    user_content = question if not facts_line else (
        f"Вопрос пользователя: {question}\nКонтекст обращения из CRM: {facts_line}"
    )
    try:
        raw = llm_provider.chat_completion(
            messages=[
                {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            max_tokens=120,
            temperature=0.0,
        )
    except Exception as exc:
        logger.warning("[SUPPORT] перезапись запроса не удалась (%s) — берём исходный вопрос", exc)
        return question
    rewritten = (raw or "").strip().strip('"')
    if rewritten and rewritten != question:
        logger.info("[SUPPORT] rewrite: %r -> %r", question, rewritten)
    return rewritten or question


def _build_doc_context(kept: list[dict]) -> str:
    blocks = []
    for i, c in enumerate(kept, 1):
        blocks.append(
            f"[{i}] файл: {c['meta_file']} | раздел: {c['meta_section']} "
            f"(cosine={c['score']:.3f})\n{c['text']}"
        )
    return "\n\n".join(blocks)


def refusal(cfg: SupportConfig, crm: dict) -> str:
    """Отказ вместо выдуманного ответа. LLM в этой ветке не вызывается."""
    text = (
        f"В документации {cfg.product_name} не нашлось раздела, релевантного этому вопросу, "
        f"поэтому отвечать наугад не буду."
    )
    if crm.get("found") and crm["facts"].get("ticket_id"):
        text += (
            f" Передаю обращение {crm['facts']['ticket_id']} инженеру и вернусь с ответом. "
            f"Если можете — приложите точный текст ошибки и время попытки."
        )
    else:
        text += (
            " Уточните вопрос или пришлите код ошибки с экрана — по нему причина определяется "
            "однозначно. Могу передать обращение инженеру."
        )
    return text


def _load_crm(ticket_id: str | None, user_id: str | None, cfg: SupportConfig) -> dict:
    """Контекст клиента из CRM (через MCP). Тикет приоритетнее пользователя: он несёт и то и другое."""
    if ticket_id:
        crm = crm_context.ticket_context(ticket_id, cfg.crm_dir)
        if not crm["found"]:
            logger.warning("[SUPPORT] %s", crm["reason"])
        return crm
    if user_id:
        crm = crm_context.user_context(user_id, cfg.crm_dir)
        if not crm["found"]:
            logger.warning("[SUPPORT] %s", crm["reason"])
        return crm
    return {"text": "", "facts": {}, "found": False, "reason": "контекст клиента не задан"}


def answer_support(
    cfg: SupportConfig,
    question: str,
    ticket_id: str | None = None,
    user_id: str | None = None,
    max_tokens: int = 800,
) -> dict:
    """Отвечает на один вопрос поддержки. Возвращает ответ, источники и диагностику."""
    crm = _load_crm(ticket_id, user_id, cfg)
    rewritten = _rewrite(question, crm["facts"])
    search = retrieve(cfg, rewritten)

    base = {
        "rewritten_query": rewritten,
        "max_score": search["max_score"],
        "max_rerank": search.get("max_rerank"),
        "crm_context": crm["text"],
        "crm_found": crm["found"],
        "provider": llm_provider.current_label(),
    }

    if not search["threshold_passed"] or not search["kept"]:
        logger.info("[SUPPORT] порог не пройден (max cosine %.4f) — отказ", search["max_score"])
        return {**base, "answer": refusal(cfg, crm), "sources": [], "threshold_passed": False}

    kept = search["kept"]
    crm_block = crm["text"] or "(обращение не привязано к тикету — общий вопрос без контекста клиента)"
    user_prompt = (
        f"# Выдержки из документации {cfg.product_name}\n{_build_doc_context(kept)}\n\n"
        f"# Контекст клиента из CRM (получен через MCP)\n{crm_block}\n\n"
        f"# Вопрос пользователя\n{question}"
    )

    answer = llm_provider.chat_completion(
        messages=[
            {"role": "system", "content": ANSWER_SYSTEM_PROMPT.format(name=cfg.product_name)},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=max_tokens,
        temperature=0.2,
    )

    sources = [
        {"chunk_id": c["chunk_id"], "meta_file": c["meta_file"], "meta_section": c["meta_section"],
         "score": c["score"], "rerank_score": c.get("rerank_score")}
        for c in kept
    ]
    return {**base, "answer": (answer or "").strip() or refusal(cfg, crm),
            "sources": sources, "threshold_passed": True}
