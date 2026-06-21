#!/usr/bin/env python3
"""
Demo: Multi-Agent Task Pipeline

Same lifecycle as demo_state_machine.py (planning -> execution -> validation -> done),
but here EACH STAGE GETS ITS OWN DeepSeekAgent instance with its own memory_dir:

  planning agent  -> produces plan_text, discarded after /ready
  execution agent  -> sees ONLY plan_text (+ invariants), produces structure_text, discarded after /validate
  validation agent -> sees ONLY plan_text + structure_text (+ invariants), produces validation_text
  done agent       -> sees ONLY plan_text + structure_text + validation_text

No agent ever sees a previous stage's raw dialogue — only the explicit handoff text the
orchestrator (TaskPipeline in pipeline.py) passes along. Each agent's own memory files live
under .memory_pipeline_<run_id>_<stage>_<round>/.

This is a throwaway demo: each run creates fresh memory files (run_id = timestamp). main.py's
pipeline is the persistent one (.memory_pipeline_* dirs survive across runs there).

Default task is an Android app with tech stack/architecture/invariants pre-seeded directly into
pipeline.invariants before the planning agent is spawned — skips the "what are your invariants?"
question in PLANNING (Step 0 only fires when the [HARD INVARIANTS] block is empty).
"""

from pipeline import TaskPipeline

DEFAULT_TASK = "Create an Android app for tracking personal expenses"
DEFAULT_INVARIANTS = [
    "Must be a native Android app",
    "Tech stack: Kotlin + Jetpack Compose",
    "Architecture: MVVM with Repository pattern",
    "Local storage only (Room database) — no backend/network calls",
]


def print_header(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def run_demo():
    print_header("Multi-Agent Task Pipeline Demo")
    print("planning-agent -> execution-agent -> validation-agent -> done-agent")
    print("Each arrow = a brand-new DeepSeekAgent with its own empty memory.")
    print("Commands: ready | validate | fix | reopen | status | exit")
    print("(NOTE: these must match exactly — typing other phrasing like 'looks good' keeps")
    print(" chatting with the planning agent instead of advancing the stage.)")
    print()

    task_desc = input("📋 Enter task description (or press Enter for default Android app): ").strip()
    use_default = not task_desc
    if use_default:
        task_desc = DEFAULT_TASK

    print(f"\n🚀 Starting task: {task_desc}")
    pipeline = TaskPipeline(task_desc)

    if use_default:
        pipeline.invariants = list(DEFAULT_INVARIANTS)
        print("📌 Pre-seeded invariants (skips the ask-for-invariants step in PLANNING):")
        for inv in pipeline.invariants:
            print(f"  - {inv}")

    print("\n🧠 Spawning PLANNING agent (agent #1, empty memory)...")
    response, metrics = pipeline.start_planning()
    print(f"\n[PLANNING — agent #1]\n{response}")
    print(f"Tokens: {metrics['total_tokens']}")

    while True:
        try:
            raw_input_text = input("\n> ").strip()
            user_input = raw_input_text.lower()

            if not user_input:
                continue

            if user_input in ("exit", "quit"):
                print("\n👋 Goodbye!")
                break

            elif user_input == "status":
                status = pipeline.status()
                print("\n📊 Pipeline Status:")
                for k, v in status.items():
                    print(f"  {k}: {v}")
                continue

            elif user_input in ("ready", "ready to execute"):
                if pipeline.stage != "planning":
                    print(f"⚠️  Not in planning stage (current stage: '{pipeline.stage}').")
                    continue
                pipeline.finalize_planning()
                print("✓ Plan captured from agent #1's last message. Agent #1 discarded (dialogue not carried forward).")
                print("\n🧠 Spawning EXECUTION agent (agent #2, empty memory — does NOT see planning dialogue)...")
                response, metrics = pipeline.run_execution()
                print(f"\n[EXECUTION — agent #2]\n{response}")
                print(f"Tokens: {metrics['total_tokens']}")
                continue

            elif user_input in ("validate", "validate this"):
                if pipeline.stage != "execution":
                    print(f"⚠️  Not in execution stage (current stage: '{pipeline.stage}'). Type 'ready' first.")
                    continue
                print("\n🧠 Spawning VALIDATION agent (agent #3, empty memory — sees only plan + structure)...")
                response, metrics, is_valid = pipeline.run_validation()
                print(f"\n[VALIDATION — agent #3]\n{response}")
                print(f"Tokens: {metrics['total_tokens']}")
                if is_valid:
                    print("\n✅ Valid & invariants OK.")
                    print("\n🧠 Spawning DONE agent (agent #4, empty memory — sees only plan + structure + validation)...")
                    response, metrics = pipeline.run_done()
                    print(f"\n[DONE — agent #4]\n{response}")
                    print(f"Tokens: {metrics['total_tokens']}")
                    print("\n🏁 Task is DONE. 'fix' is no longer available here — type 'reopen' if you want")
                    print("   to revise the finished solution (goes back to PLANNING with the prior")
                    print("   plan/structure/validation handed to a fresh planning agent as context).")
                else:
                    print("\n❌ Issues found / invariants violated. Type 'fix' to spawn a correction agent.")
                continue

            elif user_input == "fix":
                if pipeline.stage != "validation":
                    if pipeline.stage == "done":
                        print("⚠️  Task is already DONE — 'fix' only applies right after a failed 'validate'. "
                              "Use 'reopen' to revise a finished task instead.")
                    else:
                        print(f"⚠️  Not in validation stage (current stage: '{pipeline.stage}'). Run 'validate' first.")
                    continue
                print(f"\n🧠 Spawning EXECUTION agent (round {pipeline.validation_round}, empty memory — "
                      f"fed ONLY the validation issue list, not agent #2's or #3's dialogue)...")
                response, metrics = pipeline.run_execution(corrections=pipeline.validation_text)
                print(f"\n[EXECUTION: corrections]\n{response}")
                print(f"Tokens: {metrics['total_tokens']}")
                continue

            elif user_input == "reopen":
                if pipeline.stage != "done":
                    print(f"⚠️  'reopen' only applies to a finished task (current stage: '{pipeline.stage}').")
                    continue
                revision_request = input("📝 What should be revised? (Enter for none): ").strip()
                print("\n🧠 Spawning PLANNING agent (new epoch, empty memory — fed the prior plan/"
                      "structure/validation as context, not the discarded dialogue)...")
                response, metrics = pipeline.reopen_planning(revision_request or None)
                print(f"\n[PLANNING — agent #1 (reopened)]\n{response}")
                print(f"Tokens: {metrics['total_tokens']}")
                continue

            elif pipeline.stage == "planning":
                # Plain chat continues the planning conversation (e.g. answering the
                # invariants question) — still agent #1, still its own isolated memory.
                response, metrics = pipeline.chat_planning(raw_input_text)
                print(f"\n[PLANNING — agent #1]\n{response}")
                print(f"Tokens: {metrics['total_tokens']}")

            else:
                print("Unknown command. Use: ready | validate | fix | status | exit")

        except KeyboardInterrupt:
            print("\nInterrupted. Type 'exit' to quit.")
        except RuntimeError as e:
            # Transition guard refused an illegal jump — show it and keep the session alive
            # instead of letting it bubble up and kill the whole demo.
            print(f"\n⛔ {e}")


if __name__ == "__main__":
    try:
        run_demo()
    except KeyboardInterrupt:
        print("\nDemo interrupted.")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
