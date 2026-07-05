"""Auto-eval v3: structured answer (Ответ/Цитаты/Источники) + hard relevance threshold
("не знаю" mode) on 10 questions (8 in-book + 2 out-of-book control questions) -> report_v3.md."""

import json
import logging
import os

from agent_v2 import ask_agent_v2, HARD_REFUSAL_ANSWER
from generation_v3 import ANSWER_HEADING, QUOTES_HEADING, SOURCES_HEADING
from retrieval_v2 import SIMILARITY_THRESHOLD

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
QUESTIONS_PATH = os.path.join(_SCRIPT_DIR, "eval_questions_v3.json")
REPORT_PATH = os.path.join(_SCRIPT_DIR, "report_v3.md")
STRATEGY = "structural"
ANSWER_LANGUAGE = "English"


def _md_cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", "<br>")


def load_questions(path: str = QUESTIONS_PATH) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def validate_result(q: dict, result: dict) -> dict:
    """Check the three things Step 3 asks for:
    1) does the answer carry a Sources block, 2) a Quotes block,
    3) did the hard 'I don't know' cutoff fire when (and only when) it should have."""
    answer = result["answer"]
    has_sources_block = SOURCES_HEADING in answer
    has_quotes_block = QUOTES_HEADING in answer
    has_answer_block = ANSWER_HEADING in answer
    refusal_triggered = result["hard_refusal"] or answer.strip() == HARD_REFUSAL_ANSWER

    expected_in_book = q["in_book"]
    if expected_in_book:
        # in-book question: must NOT refuse, and must show its structured work
        threshold_ok = not refusal_triggered
        structure_ok = has_answer_block and has_quotes_block and has_sources_block
    else:
        # out-of-book question: refusal MUST fire, and it must fire BEFORE any structured
        # answer is produced (no point checking quote/source blocks — there's no LLM call)
        threshold_ok = refusal_triggered
        structure_ok = True

    passed = threshold_ok and structure_ok

    return {
        "has_sources_block": has_sources_block,
        "has_quotes_block": has_quotes_block,
        "has_answer_block": has_answer_block,
        "refusal_triggered": refusal_triggered,
        "threshold_ok": threshold_ok,
        "structure_ok": structure_ok,
        "passed": passed,
    }


def run_evaluation(questions: list[dict], strategy: str = STRATEGY) -> list[dict]:
    results = []
    for q in questions:
        tag = "IN-BOOK" if q["in_book"] else "OUT-OF-BOOK (expect refusal)"
        print(f"\n{'=' * 90}\nQ{q['id']} [{tag}]: {q['question']}\n{'=' * 90}")

        result = ask_agent_v2(q["question"], mode="advanced", strategy=strategy, language=ANSWER_LANGUAGE)
        validation = validate_result(q, result)

        logger.info(
            "[VALIDATE] Q%d — max_score=%.4f threshold=%.2f refusal=%s sources_block=%s quotes_block=%s -> %s",
            q["id"], result["max_score"] or 0.0, SIMILARITY_THRESHOLD, validation["refusal_triggered"],
            validation["has_sources_block"], validation["has_quotes_block"],
            "PASS" if validation["passed"] else "FAIL",
        )

        results.append({
            "id": q["id"],
            "question": q["question"],
            "in_book": q["in_book"],
            "rewritten_query": result["rewritten_query"],
            "answer": result["answer"],
            "sources": result["sources"],
            "max_score": result["max_score"],
            "threshold_passed": result["threshold_passed"],
            "hard_refusal": result["hard_refusal"],
            "validation": validation,
        })
    return results


def write_report(results: list[dict], path: str = REPORT_PATH) -> None:
    total = len(results)
    passed = sum(1 for r in results if r["validation"]["passed"])

    lines = [
        "# RAG Evaluation Report v3 — Structured Citations + Hard Relevance Threshold",
        "",
        f"Strategy: `{STRATEGY}` | Similarity threshold: `{SIMILARITY_THRESHOLD}` | "
        f"Answer language forced to: `{ANSWER_LANGUAGE}`",
        "",
        f"**Итог валидации: {passed}/{total} вопросов прошли проверку.**",
        "",
        "Проверка на каждый вопрос:",
        "1. **Источники** — присутствует ли блок `## Sources` с chunk_id/source/section.",
        "2. **Цитаты** — присутствует ли блок `## Quotes Used` с дословными выдержками.",
        "3. **Порог/Не знаю** — сработал ли режим отказа корректно (должен сработать ТОЛЬКО на "
        "вопросах вне книги, где max cosine similarity ниже порога).",
        "",
        "| # | Вопрос | В книге? | Max cosine | Порог пройден? | Режим 'Не знаю'? | Есть цитаты? | Есть источники? | Валидация | Ответ модели |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]

    for r in results:
        v = r["validation"]
        max_score_str = f"{r['max_score']:.4f}" if r["max_score"] is not None else "—"
        lines.append(
            "| {id} | {q} | {in_book} | {score} | {thr} | {refusal} | {quotes} | {sources} | {verdict} | {answer} |".format(
                id=r["id"],
                q=_md_cell(r["question"]),
                in_book="Да" if r["in_book"] else "Нет",
                score=max_score_str,
                thr="Да" if r["threshold_passed"] else "Нет",
                refusal="Да" if r["hard_refusal"] else "Нет",
                quotes="Да" if v["has_quotes_block"] else "Нет",
                sources="Да" if v["has_sources_block"] else "Нет",
                verdict="✅ PASS" if v["passed"] else "❌ FAIL",
                answer=_md_cell(r["answer"][:500]),
            )
        )

    lines += [
        "",
        "## Как это страхует от галлюцинаций",
        "",
        "- Блок **\"Использованные цитаты\"** заставляет модель предъявить дословный текст из "
        "книги, подтверждающий ответ — придуманный факт негде подкрепить дословной цитатой, "
        "поэтому расхождение видно сразу при чтении отчёта.",
        "- Блок **\"Источники\"** привязывает каждый ответ к конкретным `chunk_id`/`section`/"
        "`source`, что даёт возможность проверить ответ по первоисточнику вручную.",
        f"- **Порог схожести ({SIMILARITY_THRESHOLD})** отсекает вопросы не по теме книги ДО "
        "обращения к DeepSeek API — вместо возможной галлюцинации система гарантированно "
        "возвращает стандартный отказ.",
    ]

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    logger.info("Report written to %s", path)


def print_console_summary(results: list[dict]) -> None:
    print("\n" + "=" * 100)
    print("  RAG v3 EVALUATION SUMMARY — Structured citations + hard threshold")
    print("=" * 100)
    passed = sum(1 for r in results if r["validation"]["passed"])
    print(f"Passed {passed}/{len(results)} validations.\n")
    for r in results:
        v = r["validation"]
        print(f"[{r['id']}] {r['question']}")
        print(f"  in_book={r['in_book']}  max_score={r['max_score']}  threshold_passed={r['threshold_passed']}  hard_refusal={r['hard_refusal']}")
        print(f"  has_quotes_block={v['has_quotes_block']}  has_sources_block={v['has_sources_block']}  -> {'PASS' if v['passed'] else 'FAIL'}")
        print(f"  Answer: {r['answer'][:200]}")
        print()
    print("=" * 100 + "\n")


def main() -> None:
    questions = load_questions()
    results = run_evaluation(questions)
    print_console_summary(results)
    write_report(results)


if __name__ == "__main__":
    main()
