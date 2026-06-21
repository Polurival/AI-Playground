from agent import DeepSeekAgent
from memory import MemoryEngine
from pipeline import TaskPipeline


def print_banner():
    print("\n" + "=" * 70)
    print("DeepSeek Agent - Multi-Layer Memory with Dynamic Context Assembly")
    print("=" * 70)
    print("Layers: Short-term (dialogue tree) | Working (task context) | Long-term (profiles)")
    print()


def print_help():
    print("""
[SHORT-TERM DIALOGUE TREE COMMANDS]
  /checkpoint <name>         Create save point of current dialogue
  /branch <name>             Spawn new chat path from checkpoint
  /switch-branch <name>      Jump to alternate conversation timeline

[LONG-TERM PROFILE COMMANDS]
  /remember <text>           Add permanent fact to active profile
  /switch-profile <name>     Switch global user traits (create if new)
  /meta <key> <value>        Set profile behavioral meta-setting:
                               - tone (e.g., "Strict and concise")
                               - format_preference (e.g., "Code-only")
                               - verbosity (e.g., "Low", "Medium", "High")
  /meta-show                 Display current profile's meta-settings

[WORKING MEMORY COMMANDS]
  /task <text>               Set or overwrite active target task

[TASK PIPELINE — separate agent per stage, no shared dialogue]
  /start-task <description>  Start pipeline. Spawns a fresh PLANNING agent.
  /ready                     Finalize plan, discard planning agent, spawn fresh EXECUTION agent.
  /validate                  Spawn fresh VALIDATION agent (sees only plan+structure, not dialogue).
                              Auto-advances to a fresh DONE agent if valid & invariants OK.
  /fix                       Spawn a fresh EXECUTION agent fed last validation's issue list.
  /reopen [revision text]    From DONE only: back to a fresh PLANNING agent fed the prior
                              plan/structure/validation as context (revise a finished task).
  /pipeline-status           Show current pipeline stage & handoff state.
                              (Plain chat during the planning stage talks to the planning agent.)

[MODE TOGGLE]
  /mode <mode_name>          Select assembly strategy:
                               - short_only (Short-term only)
                               - short_working (Short-term + Working)
                               - short_long (Short-term + Long-term)
                               - full_memory (All three layers)

[STATUS & INFO]
  /status                    Show current configuration
  /branches                  List available dialogue branches
  /profiles                  List available long-term profiles
  /help                      Show this help

[EXIT]
  /exit or /quit             Exit program
""")


def print_metrics(metrics: dict) -> None:
    """Display token usage and memory state."""
    print("\n[TOKENS]")
    print(f"  User input: {metrics['user_input_tokens']} | Context: {metrics['context_tokens']} | "
          f"Completion: {metrics['completion_tokens']} | Total: {metrics['total_tokens']}")

    debug = metrics.get("memory_debug", {})
    print(f"\n[MEMORY STATE]")
    print(f"  Assembly mode: {debug.get('assembly_mode')}")

    st = debug.get("short_term", {})
    print(f"  Short-term: branch='{st.get('current_branch')}' branches={st.get('branches_count')} context={st.get('total_context')}")

    wk = debug.get("working", {})
    print(f"  Working: has_task={wk.get('has_task')} context_keys={wk.get('context_keys')}")

    lt = debug.get("long_term", {})
    print(f"  Long-term: profile='{lt.get('current_profile')}' profiles={lt.get('profiles_count')} facts={lt.get('facts_in_current')}\n")


def main():
    print_banner()

    try:
        agent = DeepSeekAgent()
        pipeline: TaskPipeline | None = None
        print("✓ Agent initialized with multi-layer memory")
        print("✓ Type '/help' for commands\n")

        while True:
            try:
                user_input = input("You: ").strip()

                if not user_input:
                    continue

                # Handle commands
                if user_input.startswith("/"):
                    parts = user_input.split(None, 1)
                    cmd = parts[0].lower()
                    arg = parts[1] if len(parts) > 1 else ""

                    if cmd in ["/exit", "/quit"]:
                        print("Goodbye!")
                        break

                    elif cmd == "/help":
                        print_help()

                    elif cmd == "/status":
                        status = agent.status()
                        print(f"\n[SHORT-TERM]")
                        print(f"  Current branch: {status['current_branch']}")
                        print(f"  Available branches: {', '.join(status['short_term_branches'])}")
                        print(f"\n[LONG-TERM]")
                        print(f"  Current profile: {status['current_profile']}")
                        print(f"  Available profiles: {', '.join(status['long_term_profiles'])}")
                        meta = status['profile_meta_settings']
                        print(f"\n[PROFILE META-SETTINGS]")
                        print(f"  Tone: {meta.get('tone')}")
                        print(f"  Format Preference: {meta.get('format_preference')}")
                        print(f"  Verbosity: {meta.get('verbosity')}")
                        print(f"\n[ASSEMBLY]")
                        print(f"  Mode: {status['assembly_mode']}")
                        print(f"  Modes available: {', '.join(MemoryEngine.ASSEMBLY_MODES.keys())}\n")

                    elif cmd == "/checkpoint":
                        if not arg:
                            print("Usage: /checkpoint <name>")
                        else:
                            agent.checkpoint(arg)
                            print(f"✓ Checkpoint '{arg}' created")

                    elif cmd == "/branch":
                        if not arg:
                            print("Usage: /branch <name>")
                        else:
                            agent.switch_branch(arg)
                            print(f"✓ Switched to branch '{arg}'")

                    elif cmd == "/switch-branch":
                        if not arg:
                            print("Usage: /switch-branch <name>")
                        else:
                            agent.switch_branch(arg)
                            print(f"✓ Switched to branch '{arg}'")

                    elif cmd == "/branches":
                        branches = agent.memory.short_term.list_branches()
                        print(f"Available branches: {', '.join(branches)}\n")

                    elif cmd == "/remember":
                        if not arg:
                            print("Usage: /remember <text>")
                        else:
                            agent.remember(arg)
                            print(f"✓ Fact recorded in profile '{agent.memory.long_term.current_profile}'")

                    elif cmd == "/switch-profile":
                        if not arg:
                            print("Usage: /switch-profile <name>")
                        else:
                            agent.switch_profile(arg)
                            print(f"✓ Switched to profile '{arg}'")

                    elif cmd == "/task":
                        if not arg:
                            print("Usage: /task <text>")
                        else:
                            agent.set_task(arg)
                            print(f"✓ Task set")

                    elif cmd == "/mode":
                        if not arg:
                            print(f"Current mode: {agent.memory.assembly_mode}")
                            print(f"Available: {', '.join(MemoryEngine.ASSEMBLY_MODES.keys())}")
                        else:
                            if agent.set_mode(arg):
                                print(f"✓ Mode set to '{arg}'")
                            else:
                                print(f"✗ Invalid mode. Available: {', '.join(MemoryEngine.ASSEMBLY_MODES.keys())}")

                    elif cmd == "/profiles":
                        profiles = agent.memory.long_term.list_profiles()
                        print(f"Available profiles: {', '.join(profiles)}\n")

                    elif cmd == "/meta":
                        if not arg:
                            print("Usage: /meta <key> <value>")
                            print("Keys: tone, format_preference, verbosity")
                        else:
                            parts = arg.split(None, 1)
                            if len(parts) < 2:
                                print("Usage: /meta <key> <value>")
                            else:
                                key, value = parts[0], parts[1]
                                agent.set_meta_setting(key, value)
                                print(f"✓ Meta-setting '{key}' updated")

                    elif cmd == "/meta-show":
                        meta = agent.get_meta_settings()
                        print(f"\n[Profile: {agent.memory.long_term.current_profile}]")
                        print(f"  Tone: {meta.get('tone')}")
                        print(f"  Format Preference: {meta.get('format_preference')}")
                        print(f"  Verbosity: {meta.get('verbosity')}\n")

                    elif cmd == "/start-task":
                        if not arg:
                            print("Usage: /start-task <description>")
                        else:
                            pipeline = TaskPipeline(arg)
                            response, metrics = pipeline.start_planning()
                            print(f"\n[PLANNING — agent #1] {response}")
                            print_metrics(metrics)

                    elif cmd == "/ready":
                        if pipeline is None or pipeline.stage != "planning":
                            print("✗ No task in PLANNING stage. Use /start-task first.")
                        else:
                            pipeline.finalize_planning()
                            print("✓ Plan captured. Planning agent discarded.")
                            response, metrics = pipeline.run_execution()
                            print(f"\n[EXECUTION — agent #2, fresh memory] {response}")
                            print_metrics(metrics)

                    elif cmd == "/validate":
                        if pipeline is None or pipeline.structure_text is None:
                            print("✗ No structure to validate yet. Use /ready first.")
                        else:
                            response, metrics, is_valid = pipeline.run_validation()
                            print(f"\n[VALIDATION — agent #3, fresh memory] {response}")
                            print_metrics(metrics)
                            if is_valid:
                                print("\n✓ Valid & invariants OK. Spawning DONE agent...")
                                response, metrics = pipeline.run_done()
                                print(f"\n[DONE — agent #4, fresh memory] {response}")
                                print_metrics(metrics)
                            else:
                                print("\n✗ Issues found (or invariants violated). Use /fix to spawn a correction agent.")

                    elif cmd == "/fix":
                        if pipeline is None or pipeline.validation_text is None:
                            print("✗ Nothing to fix. Run /validate first.")
                        else:
                            response, metrics = pipeline.run_execution(corrections=pipeline.validation_text)
                            print(f"\n[EXECUTION: corrections — fresh agent, round {pipeline.validation_round}] {response}")
                            print_metrics(metrics)

                    elif cmd == "/reopen":
                        if pipeline is None or pipeline.stage != "done":
                            print(f"✗ 'reopen' only applies to a finished task "
                                  f"(current stage: '{pipeline.stage if pipeline else 'none'}').")
                        else:
                            response, metrics = pipeline.reopen_planning(arg or None)
                            print(f"\n[PLANNING — agent #1 (reopened), fresh memory] {response}")
                            print_metrics(metrics)

                    elif cmd == "/pipeline-status":
                        if pipeline is None:
                            print("✗ No active pipeline. Use /start-task to begin.")
                        else:
                            status = pipeline.status()
                            print(f"\n[PIPELINE STATUS]")
                            print(f"  Task: {status['task_description']}")
                            print(f"  Stage: {status['stage']}")
                            print(f"  Validation round: {status['validation_round']}")
                            print(f"  Invariants: {status['invariants']}")
                            print(f"  Invariants satisfied: {status['invariants_satisfied']}")
                            print(f"  Has plan / structure / validation: "
                                  f"{status['has_plan']} / {status['has_structure']} / {status['has_validation']}\n")

                    else:
                        print(f"Unknown command: {cmd}. Type '/help' for list.")

                else:
                    if pipeline is not None and pipeline.stage == "planning":
                        # Plain chat during planning goes to the planning-stage agent only.
                        response, metrics = pipeline.chat_planning(user_input)
                        print(f"\n[PLANNING — agent #1] {response}")
                        print_metrics(metrics)
                    else:
                        # No active pipeline (or pipeline past planning) -> general chat agent.
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
