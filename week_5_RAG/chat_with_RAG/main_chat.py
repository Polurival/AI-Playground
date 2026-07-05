"""Step 3 — interactive RAG chat CLI.

Run:  python3 main_chat.py
Type your questions about "Alice's Adventures in Wonderland". Every turn shows the colour-coded
RAG stages (state update -> rewrite -> retrieve -> threshold -> rerank -> answer), then the
structured answer (Answer / Quotes Used / Sources) and the current Task State.

Commands:
  /state   show the current Task State panel
  /reset   start a fresh conversation (clears history + task state)
  /exit    quit
"""

import logging

from chat_agent import ChatAgent
from ui import setup_logging, render_answer, render_task_state, rule, BOLD, RESET, GREY, RED, BRIGHT_GREEN, YELLOW


def _print_result(result: dict) -> None:
    print()
    if result["hard_refusal"]:
        print(f"{RED}{BOLD}[I DON'T KNOW — relevance below threshold, DeepSeek not called]{RESET}")
        print(result["answer"])
    else:
        print(render_answer(result["answer"]))
        if result["sources"]:
            print(f"\n{GREY}source metadata (verify quotes are not invented):{RESET}")
            for s in result["sources"]:
                rr = s.get("rerank_score")
                rr_str = f"{rr:.4f}" if isinstance(rr, float) else str(rr)
                print(
                    f"{GREY}  chunk_id={s['chunk_id']} | section={s['meta_section']} "
                    f"| cosine={s['score']:.4f} | rerank={rr_str}{RESET}"
                )

    print()
    print(render_task_state(result["task_state"]))
    print(rule())


def main() -> None:
    setup_logging(logging.INFO)
    agent = ChatAgent(strategy="structural", language="English")

    print(rule())
    print(f"{BOLD}{BRIGHT_GREEN}  RAG CHAT — Alice's Adventures in Wonderland{RESET}")
    print(f"{GREY}  stateful chat over the RAG engine (rewrite + threshold + rerank + structured answer){RESET}")
    print(f"{GREY}  commands: /state  /reset  /exit{RESET}")
    print(rule())

    while True:
        try:
            user_text = input(f"\n{BOLD}{YELLOW}You:{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not user_text:
            continue
        if user_text.lower() == "/exit":
            print("Bye.")
            break
        if user_text.lower() == "/state":
            print(render_task_state(agent.task_state.to_dict()))
            continue
        if user_text.lower() == "/reset":
            agent = ChatAgent(strategy="structural", language="English")
            print(f"{GREY}(conversation reset — history and task state cleared){RESET}")
            continue

        print(rule("-"))
        result = agent.ask(user_text)
        _print_result(result)


if __name__ == "__main__":
    main()
