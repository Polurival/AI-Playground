from agent import DeepSeekAgent


def print_header():
    """Display welcome header."""
    print("\n" + "=" * 60)
    print("DeepSeek Agent - Multi-Strategy Context Management")
    print("=" * 60)


def print_metrics(metrics: dict) -> None:
    """Display token usage and strategy state metrics."""
    print("\n[Memory State]")
    debug = metrics.get("strategy_debug", {})
    if metrics["strategy"] == "sliding_window":
        print(f"  - Messages in window: {debug.get('context_size', 0)}")
        print(f"  - Window capacity: {debug.get('window_size', 0)}")
    elif metrics["strategy"] == "sticky_facts":
        print(f"  - Messages in window: {debug.get('context_size', 0)}")
        print(f"  - Facts tracked: {debug.get('facts_count', 0)}")
        print(f"  - Facts token size: {debug.get('facts_tokens', 0)}")
    elif metrics["strategy"] == "branching":
        print(f"  - Current branch: {debug.get('current_branch', 'main')}")
        print(f"  - Total branches: {debug.get('branches_count', 0)}")
        print(f"  - Messages in branch: {debug.get('messages_in_current', 0)}")

    print("\n[Token Analytics]")
    print(f"  - User input: {metrics['user_input_tokens']} tokens")
    print(f"  - Context sent: {metrics['context_tokens_before_response']} tokens")
    print(f"  - Completion: {metrics['completion_tokens_used']} tokens")
    print(f"  - Total this turn: {metrics['total_this_step']} tokens")
    print(f"  - Strategy: {metrics['strategy']}\n")


def print_help():
    """Display command help."""
    print("\n[Available Commands]")
    print("  /help                       - Show this help")
    print("  /strategy <name>            - Switch strategy (sliding_window, sticky_facts, branching)")
    print("  /checkpoint <name>          - Create checkpoint (branching only)")
    print("  /branch <name>              - Switch to branch (branching only)")
    print("  /branches                   - List all branches (branching only)")
    print("  /status                     - Show current strategy status")
    print("  /exit or /quit              - Exit the program")
    print()


def show_strategy_menu() -> str:
    """Display strategy selection menu and return user choice."""
    print("\nSelect Context Management Strategy:")
    print("  1. Sliding Window     - Keep last N messages")
    print("  2. Sticky Facts       - Maintain key-value memory of facts")
    print("  3. Branching          - Create conversation branches/checkpoints")
    print()

    while True:
        choice = input("Enter choice (1-3): ").strip()
        if choice == "1":
            return "sliding_window"
        elif choice == "2":
            return "sticky_facts"
        elif choice == "3":
            return "branching"
        else:
            print("Invalid choice. Please enter 1, 2, or 3.")


def show_strategy_config(strategy: str) -> dict:
    """Display configuration options for selected strategy."""
    config = {}

    print(f"\n[Configuring {strategy}]")

    if strategy == "branching":
        config["window_size"] = 6  # Default, not used for branching
        print(f"✓ Will support checkpoints with independent full-history branches")
    else:
        window_size = input("Enter window size (default 6): ").strip()
        config["window_size"] = int(window_size) if window_size.isdigit() else 6

        if strategy == "sliding_window":
            print(f"✓ Will keep last {config['window_size']} messages")
        elif strategy == "sticky_facts":
            print(f"✓ Will maintain facts + last {config['window_size']} messages")

    return config


def main():
    """Main CLI loop."""
    print_header()

    try:
        # Strategy selection
        selected_strategy = show_strategy_menu()
        config = show_strategy_config(selected_strategy)

        # Initialize agent
        agent = DeepSeekAgent(
            strategy=selected_strategy,
            window_size=config["window_size"]
        )

        print(f"\n✓ Agent initialized with '{selected_strategy}' strategy (window_size={config['window_size']})")
        print("Type '/help' for commands. Enter '/exit' to quit.\n")

        while True:
            try:
                user_input = input("You: ").strip()

                # Handle empty input
                if not user_input:
                    continue

                # Handle commands
                if user_input.startswith("/"):
                    cmd_parts = user_input.split(None, 1)
                    command = cmd_parts[0].lower()
                    arg = cmd_parts[1] if len(cmd_parts) > 1 else ""

                    if command in ["/exit", "/quit"]:
                        print("Goodbye!")
                        break

                    elif command == "/help":
                        print_help()

                    elif command == "/status":
                        print(f"\nCurrent Strategy: {agent.get_current_strategy()}")
                        if isinstance(agent.strategy, type(agent.STRATEGIES["branching"])()):
                            branches = agent.list_branches()
                            print(f"Available Branches: {', '.join(branches)}")

                    elif command == "/strategy":
                        if not arg:
                            print("Usage: /strategy <name>")
                            print(f"Available: {', '.join(agent.STRATEGIES.keys())}")
                        else:
                            if agent.switch_strategy(arg, window_size=config["window_size"]):
                                print(f"✓ Switched to {arg} strategy")

                    elif command == "/checkpoint":
                        if not arg:
                            print("Usage: /checkpoint <name>")
                        elif agent.create_checkpoint(arg):
                            print(f"✓ Created checkpoint '{arg}'")

                    elif command == "/branch":
                        if not arg:
                            print("Usage: /branch <name>")
                        elif agent.switch_branch(arg):
                            print(f"✓ Switched to branch '{arg}' (creates if new)")

                    elif command == "/branches":
                        branches = agent.list_branches()
                        if branches:
                            print(f"Available branches: {', '.join(branches)}")
                        else:
                            print("Branches not available in current strategy")

                    else:
                        print(f"Unknown command: {command}. Type '/help' for available commands.")

                else:
                    # Send user message as normal
                    response, metrics = agent.send_message(user_input)
                    print(f"\nAgent: {response}")
                    print_metrics(metrics)

            except KeyboardInterrupt:
                print("\nInterrupted. Type '/exit' to quit.")
            except Exception as e:
                print(f"Error: {e}")

    except KeyboardInterrupt:
        print("\nProgram interrupted.")
    except Exception as e:
        print(f"Fatal error: {e}")


if __name__ == "__main__":
    main()
