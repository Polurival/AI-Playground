"""Auto-eval: run 10 control questions through NO-RAG and RAG modes, write report.md."""

import json
import logging
import os

from agent import ask_agent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
QUESTIONS_PATH = os.path.join(_SCRIPT_DIR, "eval_questions.json")
REPORT_PATH = os.path.join(_SCRIPT_DIR, "report.md")
STRATEGY = "structural"  # best strategy per analysis.py — one chunk per chapter, preserves scene context


def _md_cell(text: str) -> str:
    """Escape a value for a Markdown table cell."""
    return text.replace("|", "\\|").replace("\n", "<br>")


def load_questions(path: str = QUESTIONS_PATH) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run_evaluation(questions: list[dict], strategy: str = STRATEGY) -> list[dict]:
    results = []
    for q in questions:
        logger.info("=== Q%d: %s ===", q["id"], q["question"])

        logger.info("  running NO-RAG …")
        no_rag = ask_agent(q["question"], use_rag=False)

        logger.info("  running RAG (strategy=%s) …", strategy)
        rag = ask_agent(q["question"], use_rag=True, strategy=strategy)

        results.append({
            "id": q["id"],
            "question": q["question"],
            "ground_truth": q["ground_truth"],
            "expected_sources": q["sources"],
            "no_rag_answer": no_rag["answer"],
            "rag_answer": rag["answer"],
            "rag_sources": rag["sources"],
        })
    return results


def write_report(results: list[dict], path: str = REPORT_PATH) -> None:
    lines = [
        "# RAG Evaluation Report — Alice's Adventures in Wonderland",
        "",
        f"Strategy used for RAG: `{STRATEGY}`",
        "",
        "| # | Вопрос | Ожидание (Ground Truth) | Ответ без RAG | Ответ с RAG | Источники (метаданные) |",
        "|---|---|---|---|---|---|",
    ]

    for r in results:
        gt = "; ".join(r["ground_truth"])
        sources = "; ".join(f"{s['meta_section']} ({s['chunk_id']}, score={s['score']:.3f})" for s in r["rag_sources"])
        lines.append(
            "| {id} | {q} | {gt} | {no_rag} | {rag} | {src} |".format(
                id=r["id"],
                q=_md_cell(r["question"]),
                gt=_md_cell(gt),
                no_rag=_md_cell(r["no_rag_answer"]),
                rag=_md_cell(r["rag_answer"]),
                src=_md_cell(sources),
            )
        )

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    logger.info("Report written to %s", path)


def print_console_table(results: list[dict]) -> None:
    print("\n" + "=" * 100)
    print("  RAG EVALUATION — NO-RAG vs RAG")
    print("=" * 100)
    for r in results:
        print(f"\n[{r['id']}] {r['question']}")
        print(f"  Ожидание   : {'; '.join(r['ground_truth'])}")
        print(f"  Без RAG    : {r['no_rag_answer'][:300]}")
        print(f"  С RAG      : {r['rag_answer'][:300]}")
        src = ", ".join(f"{s['meta_section']} ({s['score']:.3f})" for s in r["rag_sources"])
        print(f"  Источники  : {src}")
    print("\n" + "=" * 100 + "\n")


def main() -> None:
    questions = load_questions()
    results = run_evaluation(questions)
    print_console_table(results)
    write_report(results)


if __name__ == "__main__":
    main()
