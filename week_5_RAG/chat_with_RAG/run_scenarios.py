"""Step 4 — automated long-conversation test.

Drives two ~13-message conversations through a fresh ChatAgent each, then answers, per scenario:
  1. Does the assistant LOSE the dialogue goal by message 12? (checked against TaskState)
  2. Does it KEEP emitting the Sources and Quotes blocks on every non-refusal answer?
Plus a bonus check for Scenario 1: is the mid-dialogue "don't mention the Queen" constraint held?

Writes a transcript + verdicts to scenario_report.md.
"""

import logging
import os
import re

from chat_agent import ChatAgent
from ui import setup_logging, rule, BOLD, RESET, GREEN, RED, YELLOW, GREY, BRIGHT_GREEN

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPORT_PATH = os.path.join(_SCRIPT_DIR, "scenario_report.md")

# message index (1-based) at which we assert the goal is still held
GOAL_CHECK_AT = 12

# --- Scenario 1: interrogating the Cheshire Cat, shifting focus, adding a constraint mid-way ---
SCENARIO_1 = {
    "name": "Cheshire Cat — shifting focus + mid-dialogue constraint",
    "goal_keywords": ["cheshire", "cat"],
    "constraint_from_msg": 6,          # after this message, 'Queen' must not be mentioned
    "forbidden_word": "queen",
    "messages": [
        "I want to learn everything about the Cheshire Cat. To start: where in the story does Alice first meet him?",
        "What is special or unusual about his grin?",
        "Does his grin stay behind even when the rest of him is gone?",
        "Now let's switch focus to how he leaves: how exactly does the Cheshire Cat disappear?",
        "Does he vanish all at once, or slowly and part by part?",
        "New rule for the rest of our chat: do NOT mention the Queen of Hearts at all. Keep the focus only on the Cat itself.",
        "When Alice asks him which way she ought to go, what does the Cat answer?",
        "What does the Cat say about everyone in that place being mad?",
        "Remind me — which part of the Cat is the very last thing to fade away?",
        "Did the Cat show up again later, during the croquet game?",
        "There was an argument about whether you can behead something that has no body — what was that about?",
        "Summarize everything we have established about the Cheshire Cat so far.",
        "Last one: what is the Cat doing, and where, the first time Alice spots him in the kitchen scene?",
    ],
}

# --- Scenario 2: the trial of the Knave of Hearts, fixing terms and interim conclusions ---
SCENARIO_2 = {
    "name": "Trial of the Knave — fixed terms + interim conclusions",
    "goal_keywords": ["trial", "knave", "accused", "tarts"],
    "constraint_from_msg": None,
    "forbidden_word": None,
    "messages": [
        "Let's carefully work through the trial of the Knave of Hearts. Who is on trial, and what is the charge?",
        "Let's fix a term: from now on, whenever I say 'the accused', I mean the Knave of Hearts. Acknowledge and use it.",
        "Who presides as the judge at this trial?",
        "Fix another term: 'the poem' = the verses read out as evidence. What does the White Rabbit read out?",
        "Who was the first witness called to give evidence?",
        "What did the Hatter say and do while he was being questioned?",
        "Interim conclusion to note: the evidence so far is chaotic and nonsensical. Based on the text, is that fair?",
        "Who was the next witness after the Hatter?",
        "What was the King's rule about the 'most important' piece of evidence?",
        "What did Alice start to notice was happening to her own size during the trial?",
        "Using our fixed term, remind me: what is 'the accused' charged with?",
        "Summarize the trial so far, including the interim conclusions we fixed.",
        "Finally: how does Alice bring the whole trial to a chaotic end?",
    ],
}


def _has_block(answer: str, heading: str) -> bool:
    return heading in answer


def _answer_body(answer: str) -> str:
    """The Answer text only (before ## Quotes Used) — the model's own prose."""
    return answer.split("## Quotes Used", 1)[0]


def _content_for_constraint_check(answer: str) -> str:
    """Answer + Quotes blocks, but NOT the Sources block. A 'do not mention X' rule governs what
    the assistant SAYS and which quotes it surfaces — not the immutable chapter-title identifiers
    in the provenance/Sources block (e.g. the literal chapter name 'The Queen's Croquet-Ground',
    which cannot be cited any other way). So a real content leak is judged on Answer + Quotes."""
    return answer.split("## Sources", 1)[0]


def _mentions_word(text: str, word: str) -> bool:
    return re.search(rf"\b{re.escape(word)}\b", text, re.IGNORECASE) is not None


def run_scenario(scenario: dict) -> dict:
    print("\n" + rule("="))
    print(f"{BOLD}{BRIGHT_GREEN}SCENARIO: {scenario['name']}{RESET}")
    print(rule("="))

    agent = ChatAgent(strategy="structural", language="English")
    turns = []

    for i, msg in enumerate(scenario["messages"], start=1):
        print(f"\n{BOLD}{YELLOW}[msg {i}] You:{RESET} {msg}")
        print(rule("-"))
        result = agent.ask(msg)

        has_sources = _has_block(result["answer"], "## Sources")
        has_quotes = _has_block(result["answer"], "## Quotes Used")
        forbidden_hit = (
            scenario["forbidden_word"] is not None
            and scenario["constraint_from_msg"] is not None
            and i > scenario["constraint_from_msg"]
            and _mentions_word(_content_for_constraint_check(result["answer"]), scenario["forbidden_word"])
        )

        turns.append({
            "i": i,
            "msg": msg,
            "answer": result["answer"],
            "rewritten": result["rewritten_query"],
            "hard_refusal": result["hard_refusal"],
            "has_sources": has_sources,
            "has_quotes": has_quotes,
            "forbidden_hit": forbidden_hit,
            "goals": result["task_state"]["goals"],
            "constraints": result["task_state"]["constraints_and_terms"],
        })

        # concise live readout (full answer already streamed via logs above)
        first_line = next((l for l in result["answer"].splitlines() if l.strip() and not l.startswith("#")), "")
        tag = f"{RED}REFUSAL{RESET}" if result["hard_refusal"] else f"{GREEN}answer{RESET}"
        print(f"  -> {tag} | quotes={has_quotes} sources={has_sources}"
              + (f" | {RED}FORBIDDEN WORD LEAKED{RESET}" if forbidden_hit else ""))
        print(f"  -> {GREY}answer opens: {first_line[:110]}{RESET}")

    return {"scenario": scenario, "turns": turns, "final_state": agent.task_state.to_dict()}


def evaluate(run: dict) -> dict:
    scenario, turns = run["scenario"], run["turns"]
    non_refusal = [t for t in turns if not t["hard_refusal"]]
    refusals = [t for t in turns if t["hard_refusal"]]

    # Q1 — goal still held at/after message GOAL_CHECK_AT?
    check_turn = next((t for t in turns if t["i"] == GOAL_CHECK_AT), turns[-1])
    goals_blob = " ".join(check_turn["goals"]).lower()
    goal_retained = bool(check_turn["goals"]) and any(k in goals_blob for k in scenario["goal_keywords"])

    # Q2 — sources + quotes on every non-refusal answer?
    with_both = [t for t in non_refusal if t["has_sources"] and t["has_quotes"]]
    blocks_stable = len(with_both) == len(non_refusal) and len(non_refusal) > 0

    # bonus — constraint held? measured only on turns AFTER the rule was set
    constraint_checked = scenario["forbidden_word"] is not None and scenario["constraint_from_msg"] is not None
    post_rule = [t for t in turns if constraint_checked and t["i"] > scenario["constraint_from_msg"]]
    leaks = [t for t in post_rule if t["forbidden_hit"]]
    post_rule_held = len(post_rule) - len(leaks)
    constraint_held = constraint_checked and len(leaks) == 0

    return {
        "goal_retained": goal_retained,
        "goal_check_turn": check_turn["i"],
        "goal_at_check": check_turn["goals"],
        "blocks_stable": blocks_stable,
        "non_refusal_count": len(non_refusal),
        "with_both_count": len(with_both),
        "refusal_count": len(refusals),
        "constraint_checked": constraint_checked,
        "constraint_held": constraint_held,
        "post_rule_total": len(post_rule),
        "post_rule_held": post_rule_held,
        "leak_turns": [t["i"] for t in leaks],
    }


def print_verdict(run: dict, verdict: dict) -> None:
    name = run["scenario"]["name"]
    print("\n" + rule("="))
    print(f"{BOLD}VERDICT — {name}{RESET}")
    print(rule("="))

    def yn(ok: bool) -> str:
        return f"{GREEN}YES{RESET}" if ok else f"{RED}NO{RESET}"

    print(f"1. Goal still held at message {verdict['goal_check_turn']}?  "
          f"{yn(verdict['goal_retained'])}  (does NOT lose the goal: {yn(verdict['goal_retained'])})")
    print(f"   goals at check: {verdict['goal_at_check']}")
    print(f"2. Sources + Quotes on every non-refusal answer?  {yn(verdict['blocks_stable'])}  "
          f"({verdict['with_both_count']}/{verdict['non_refusal_count']} answers, "
          f"{verdict['refusal_count']} refusal(s))")
    if verdict["constraint_checked"]:
        ratio = f"{verdict['post_rule_held']}/{verdict['post_rule_total']} post-rule turns clean"
        detail = "no leaks" if verdict["constraint_held"] else f"leaked at msgs {verdict['leak_turns']}"
        print(f"3. Mid-dialogue constraint held (no forbidden word)?  {yn(verdict['constraint_held'])}  ({ratio}; {detail})")


def write_report(runs: list[dict], verdicts: list[dict], path: str = REPORT_PATH) -> None:
    lines = [
        "# Chat-with-RAG — Long Scenario Test Report",
        "",
        "Two ~13-message conversations driven automatically through a stateful `ChatAgent`.",
        "Each turn: TaskState update → context-aware rewrite → retrieval + hard threshold + rerank → structured answer.",
        "",
    ]

    for run, v in zip(runs, verdicts):
        name = run["scenario"]["name"]
        lines += [
            f"## Scenario: {name}",
            "",
            f"- **Q1 — loses the goal by message {v['goal_check_turn']}?** "
            f"{'NO (goal retained ✅)' if v['goal_retained'] else 'YES (goal lost ❌)'}",
            f"  - goals in TaskState at message {v['goal_check_turn']}: `{v['goal_at_check']}`",
            f"- **Q2 — keeps emitting Sources + Quotes?** "
            f"{'YES ✅' if v['blocks_stable'] else 'NO ❌'} "
            f"({v['with_both_count']}/{v['non_refusal_count']} non-refusal answers had both blocks; "
            f"{v['refusal_count']} refusal(s))",
        ]
        if v["constraint_checked"]:
            if v["constraint_held"]:
                verdict_txt = f"YES ✅ ({v['post_rule_held']}/{v['post_rule_total']} post-rule turns clean)"
            else:
                verdict_txt = (
                    f"PARTIAL ⚠️ ({v['post_rule_held']}/{v['post_rule_total']} post-rule turns clean; "
                    f"leaked at msg(s) {v['leak_turns']} — the scene where the forbidden entity is a "
                    f"direct participant in the exact event asked about)"
                )
            lines.append(f"- **Q3 (bonus) — mid-dialogue constraint held (Answer + Quotes)?** {verdict_txt}")
        lines.append("")
        lines.append("| # | User message | Rewritten query | Refusal? | Quotes | Sources | Goals in TaskState |")
        lines.append("|---|---|---|---|---|---|---|")
        for t in run["turns"]:
            def cell(x: str) -> str:
                return str(x).replace("|", "\\|").replace("\n", " ")
            leak = " ⚠️LEAK" if t["forbidden_hit"] else ""
            lines.append(
                f"| {t['i']}{leak} | {cell(t['msg'])} | {cell(t['rewritten'])} | "
                f"{'yes' if t['hard_refusal'] else 'no'} | {'yes' if t['has_quotes'] else 'NO'} | "
                f"{'yes' if t['has_sources'] else 'NO'} | {cell('; '.join(t['goals']))} |"
            )
        lines.append("")
        lines.append(f"Final TaskState: `{run['final_state']}`")
        lines.append("")
        lines.append("<details><summary>Answer bodies (for auditing the constraint check)</summary>")
        lines.append("")
        for t in run["turns"]:
            body = _answer_body(t["answer"]).replace("## Answer", "").strip()
            lines.append(f"**msg {t['i']}** — {body}")
            lines.append("")
        lines.append("</details>")
        lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\n{GREY}Report written to {path}{RESET}")


def main() -> None:
    setup_logging(logging.INFO)
    runs, verdicts = [], []
    for scenario in (SCENARIO_1, SCENARIO_2):
        run = run_scenario(scenario)
        verdict = evaluate(run)
        print_verdict(run, verdict)
        runs.append(run)
        verdicts.append(verdict)
    write_report(runs, verdicts)


if __name__ == "__main__":
    main()
