#!/usr/bin/env python3
"""
Demo: Task State Machine Agent

Shows task planning → execution → validation → done flow with pause/resume.
"""

from agent import DeepSeekAgent


def print_header(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def run_state_machine_demo():
    print_header("Task State Machine Agent Demo")
    print("Modes: planning → execution → validation ⟷ execution → done")
    print("Commands: pause | resume | status | back | mark valid | exit")
    print()

    # Initialize agent with state machine enabled
    agent = DeepSeekAgent(use_state_machine=True, memory_dir=".memory_state_demo")

    # Start task
    task_desc = input("📋 Enter task description (or press Enter for default): ").strip()
    if not task_desc:
        task_desc = "Create a Spanish language learning application"

    print(f"\n🚀 Starting task: {task_desc}\n")
    response, metrics = agent.start_task(task_desc)
    print(f"[{agent.task_state.upper()}]\n{response}")
    print(f"\nTokens: {metrics['total_tokens']}")

    # Interactive loop
    while True:
        user_input = input("\n> ").strip().lower()

        if not user_input:
            continue

        # Special commands
        if user_input == "exit" or user_input == "quit":
            print("\n👋 Goodbye!")
            break

        elif user_input == "pause":
            agent.pause_task()
            print("⏸️  Task paused. Use 'resume' to continue.")
            continue

        elif user_input == "resume":
            if not agent.paused:
                print("⚠️  Task not paused")
                continue
            response, metrics = agent.resume_task()
            print(f"\n[{agent.task_state.upper()}]\n{response}")
            print(f"\nTokens: {metrics['total_tokens']}")
            continue

        elif user_input == "status":
            status = agent.task_status()
            print(f"\n📊 Task Status:")
            print(f"  Description: {status['task_description']}")
            print(f"  State: {status['current_state']}")
            print(f"  Paused: {status['paused']}")
            if status['task_plan']:
                print(f"  Plan: {status['task_plan'][:100]}...")
            if status['task_structure']:
                print(f"  Structure: {status['task_structure'][:100]}...")
            continue

        elif user_input == "back":
            state_map = {"planning": "idle", "execution": "planning", "validation": "execution", "done": "validation"}
            prev_state = state_map.get(agent.task_state)
            if prev_state:
                agent.set_task_state(prev_state)
                print(f"↩️  Returned to {prev_state} state")
            continue

        elif user_input == "mark valid":
            agent.set_task_state("done")
            print("✅ Task marked as valid. Moving to DONE state.")
            continue

        # Regular chat message
        response, metrics = agent.send_message(user_input)
        print(f"\n[{agent.task_state.upper()}]\n{response}")
        print(f"\nTokens: prompt={metrics['prompt_tokens']}, completion={metrics['completion_tokens']}, total={metrics['total_tokens']}")


if __name__ == "__main__":
    run_state_machine_demo()
