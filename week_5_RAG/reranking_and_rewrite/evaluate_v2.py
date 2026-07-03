"""Auto-eval v2: Basic RAG (Task 2) vs Advanced RAG (rewrite + broad search + rerank) -> report_v2.md."""

import json
import logging
import os

from agent_v2 import ask_agent_v2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
QUESTIONS_PATH = os.path.join(_SCRIPT_DIR, "..", "request_to_RAG", "eval_questions.json")
REPORT_PATH = os.path.join(_SCRIPT_DIR, "report_v2.md")
STRATEGY = "structural"
ANSWER_LANGUAGE = "English"  # eval questions are English; force answers to match so the report stays consistent


def _md_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", "<br>")


def load_questions(path: str = QUESTIONS_PATH) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run_evaluation(questions: list[dict], strategy: str = STRATEGY) -> list[dict]:
    results = []
    for q in questions:
        print(f"\n{'=' * 90}\nQ{q['id']}: {q['question']}\n{'=' * 90}")

        logger.info(">>> BASIC RAG (top-3, no rewrite/rerank)")
        basic = ask_agent_v2(q["question"], mode="basic", strategy=strategy, language=ANSWER_LANGUAGE)

        logger.info(">>> ADVANCED RAG (rewrite + top-10 + cross-encoder rerank -> top-3)")
        advanced = ask_agent_v2(q["question"], mode="advanced", strategy=strategy, language=ANSWER_LANGUAGE)

        results.append({
            "id": q["id"],
            "question": q["question"],
            "ground_truth": q["ground_truth"],
            "rewritten_query": advanced["rewritten_query"],
            "basic_answer": basic["answer"],
            "basic_sources": basic["sources"],
            "advanced_answer": advanced["answer"],
            "advanced_sources": advanced["sources"],
            "advanced_initial_count": advanced["initial_count"],
            "advanced_final_count": advanced["final_count"],
            "advanced_dropped_count": advanced["dropped_count"],
        })
    return results


def write_report(results: list[dict], path: str = REPORT_PATH) -> None:
    lines = [
        "# RAG Evaluation Report v2 — Basic RAG vs Advanced RAG (Rewrite + Rerank)",
        "",
        f"Strategy: `{STRATEGY}`",
        "",
        "| # | Вопрос | Исходный / Переписанный запрос | Ответ Базового RAG | Ответ Продвинутого RAG | Чанков до/после reranking |",
        "|---|---|---|---|---|---|",
    ]

    for r in results:
        query_cell = f"**Исходный:** {r['question']}<br>**Переписанный:** {r['rewritten_query']}"
        counts = f"{r['advanced_initial_count']} / {r['advanced_final_count']} (отсеяно: {r['advanced_dropped_count']})"
        lines.append(
            "| {id} | {q} | {query} | {basic} | {advanced} | {counts} |".format(
                id=r["id"],
                q=_md_cell(r["question"]),
                query=_md_cell(query_cell),
                basic=_md_cell(r["basic_answer"]),
                advanced=_md_cell(r["advanced_answer"]),
                counts=_md_cell(counts),
            )
        )

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    logger.info("Report written to %s", path)


def print_console_summary(results: list[dict]) -> None:
    print("\n" + "=" * 100)
    print("  RAG v2 EVALUATION SUMMARY — Basic vs Advanced (Rewrite + Rerank)")
    print("=" * 100)
    rewritten_count = sum(1 for r in results if r["rewritten_query"] != r["question"])
    print(f"Query rewritten in {rewritten_count}/{len(results)} questions.")
    for r in results:
        print(f"\n[{r['id']}] {r['question']}")
        if r["rewritten_query"] != r["question"]:
            print(f"  Rewrite    : {r['rewritten_query']}")
        print(f"  Chunks     : {r['advanced_initial_count']} in -> {r['advanced_final_count']} kept ({r['advanced_dropped_count']} dropped by rerank)")
        print(f"  Basic RAG  : {r['basic_answer'][:200]}")
        print(f"  Advanced   : {r['advanced_answer'][:200]}")
    print("\n" + "=" * 100 + "\n")


def main() -> None:
    questions = load_questions()
    results = run_evaluation(questions)
    print_console_summary(results)
    write_report(results)


if __name__ == "__main__":
    main()
