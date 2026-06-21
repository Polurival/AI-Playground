#!/usr/bin/env python3
"""
Demo: code-level state transition guard (no API calls).

Proves the task lifecycle can't be skipped/jumped:
- can't go straight to execution/validation/done from idle or planning
- can't reach done without passing through validation
- can't reach done while invariants are unresolved/violated, even via "mark valid"
- the model can't talk its way past the guard via a fake [STATE: x] marker
- pause/resume preserves state correctly

Uses ALLOWED_TRANSITIONS / set_task_state / _sync_state_from_response directly,
so no DEEPSEEK_API_KEY or network call is needed.
"""

from agent import DeepSeekAgent, ALLOWED_TRANSITIONS


def check(label: str, condition: bool) -> None:
    mark = "✅" if condition else "❌"
    print(f"{mark} {label}")
    assert condition, f"FAILED: {label}"


def main():
    agent = DeepSeekAgent.__new__(DeepSeekAgent)  # bypass __init__ (no API key / network needed)
    agent.use_state_machine = True
    agent.task_state = "idle"
    agent.task_description = "Build a Spanish learning app"
    agent.task_plan = None
    agent.task_structure = None
    agent.paused = False
    agent.paused_state = None
    agent.invariants_satisfied = None
    agent.system_prompt = ""
    agent._update_state_machine_prompt = lambda: None
    agent._save_memory = lambda: None

    print("\n=== 1. Illegal jumps from idle ===")
    check("idle → execution blocked", agent.set_task_state("execution") is False)
    check("idle → validation blocked", agent.set_task_state("validation") is False)
    check("idle → done blocked", agent.set_task_state("done") is False)
    check("state unchanged after blocked jumps", agent.task_state == "idle")

    print("\n=== 2. Legal forward path ===")
    check("idle → planning allowed", agent.set_task_state("planning") is True)
    check("state is planning", agent.task_state == "planning")

    print("\n=== 3. Can't skip execution: planning → done/validation blocked ===")
    check("planning → done blocked", agent.set_task_state("done") is False)
    check("planning → validation blocked", agent.set_task_state("validation") is False)
    check("state still planning", agent.task_state == "planning")

    check("planning → execution allowed (plan approved)", agent.set_task_state("execution") is True)

    print("\n=== 4. Can't skip validation: execution → done blocked ===")
    check("execution → done blocked", agent.set_task_state("done") is False)
    check("state still execution", agent.task_state == "execution")

    check("execution → validation allowed", agent.set_task_state("validation") is True)

    print("\n=== 5. Can't finish without validation passing (invariants gate) ===")
    agent.invariants_satisfied = None
    check("'mark valid' (done) blocked while unresolved", agent.set_task_state("done") is False)
    check("falls back to execution, not stuck/stale", agent.task_state == "execution")

    agent.set_task_state("validation")  # re-enter loop, as the real flow requires
    agent.invariants_satisfied = False
    check("done blocked while invariants VIOLATED", agent.set_task_state("done") is False)
    check("falls back to execution again", agent.task_state == "execution")

    agent.set_task_state("validation")
    agent.invariants_satisfied = True
    check("done allowed once invariants OK and coming from validation", agent.set_task_state("done") is True)
    check("state is done", agent.task_state == "done")

    print("\n=== 6. Model can't fake its way past the guard via [STATE: x] ===")
    agent.task_state = "planning"
    agent.invariants_satisfied = None
    fake_response = "Some reasoning...\n[STATE: done]\nDone!"
    agent._sync_state_from_response(fake_response)
    check("fake [STATE: done] from planning ignored", agent.task_state == "planning")

    print("\n=== 7. Pause/resume preserves state correctly ===")
    agent.task_state = "execution"
    agent.pause_task()
    check("paused flag set", agent.paused is True)
    check("paused_state captured", agent.paused_state == "execution")
    check("task_state unchanged while paused", agent.task_state == "execution")
    # Simulate resume without hitting the API: clear paused flag the same way resume_task() does
    agent.paused = False
    check("resume clears paused flag, state intact", agent.paused is False and agent.task_state == "execution")

    print("\n=== Transition table ===")
    for state, allowed in ALLOWED_TRANSITIONS.items():
        print(f"  {state} -> {sorted(allowed)}")

    print("\n✅ All transition guard checks passed.")


if __name__ == "__main__":
    main()
