"""Step 3 — interactive RAG chat CLI.

Run:  python3 main_chat.py
Type your questions about "Alice's Adventures in Wonderland". Every turn shows the colour-coded
RAG stages (state update -> rewrite -> retrieve -> threshold -> rerank -> answer), then the
structured answer (Answer / Quotes Used / Sources) and the current Task State.

Commands:
  /state           show the current Task State panel
  /model           show the active LLM backend
  /model local     switch generation to the local Ollama model (fully offline)
  /model deepseek  switch generation back to the cloud DeepSeek API
  /reset           start a fresh conversation (clears history + task state)
  /exit            quit
"""

import logging

from chat_agent import ChatAgent
import llm_provider
from ui import setup_logging, render_answer, render_task_state, rule, BOLD, RESET, GREY, RED, BRIGHT_GREEN, YELLOW, CYAN


def _print_result(result: dict) -> None:
    print()
    if result["hard_refusal"]:
        print(f"{RED}{BOLD}[I DON'T KNOW — relevance below threshold, no main LLM call made]{RESET}")
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
        elapsed = result.get("elapsed_s")
        elapsed_str = f"{elapsed:.2f}s" if isinstance(elapsed, float) else "n/a"
        print(f"\n{CYAN}model: {result['provider']} | generation time: {elapsed_str}{RESET}")

    print()
    print(render_task_state(result["task_state"]))
    print(rule())


def _handle_model_command(user_text: str) -> None:
    parts = user_text.split(maxsplit=1)
    if len(parts) == 1:
        print(f"{GREY}active model: {llm_provider.current_label()}{RESET}")
        print(f"{GREY}available: {', '.join(llm_provider.available_providers())} "
              f"— switch with `/model local` or `/model deepseek`{RESET}")
        return
    try:
        label = llm_provider.set_provider(parts[1])
        print(f"{GREY}(switched active model -> {label}){RESET}")
    except ValueError as exc:
        print(f"{RED}{exc}{RESET}")


def main() -> None:
    setup_logging(logging.INFO)
    agent = ChatAgent(strategy="structural", language="English")

    print(rule())
    print(f"{BOLD}{BRIGHT_GREEN}  RAG CHAT — Alice's Adventures in Wonderland{RESET}")
    print(f"{GREY}  stateful chat over the RAG engine (rewrite + threshold + rerank + structured answer){RESET}")
    print(f"{GREY}  active model: {llm_provider.current_label()}{RESET}")
    print(f"{GREY}  commands: /state  /model [local|deepseek]  /reset  /exit{RESET}")
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
        if user_text.lower().startswith("/model"):
            _handle_model_command(user_text)
            continue
        if user_text.lower() == "/reset":
            agent = ChatAgent(strategy="structural", language="English")
            print(f"{GREY}(conversation reset — history and task state cleared){RESET}")
            continue

        print(rule("-"))
        try:
            result = agent.ask(user_text)
        except Exception as exc:  # noqa: BLE001 — keep the session alive on a backend hiccup
            print(f"\n{RED}{BOLD}Error: {exc}{RESET}")
            continue
        _print_result(result)


if __name__ == "__main__":
    main()
