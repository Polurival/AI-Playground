#!/usr/bin/env python3
"""
Offline proof that TaskPipeline (pipeline.py) can't skip/jump stages, no DEEPSEEK_API_KEY needed.

Monkeypatches TaskPipeline._new_agent with a fake agent stub (canned .send_message), so we
exercise the real run_execution/run_validation/run_done guard logic without hitting the network.
"""

from pipeline import TaskPipeline, ALLOWED_TRANSITIONS


class FakeAgent:
    """Stand-in for DeepSeekAgent: same .send_message(text) -> (response, metrics) shape."""

    def __init__(self, canned_response: str):
        self.canned_response = canned_response

    def send_message(self, text):
        return self.canned_response, {"total_tokens": 0}

    def get_invariants(self):
        return []

    class _FakeShortTerm:
        @staticmethod
        def get_all_messages():
            return [{"role": "assistant", "content": "FAKE PLAN: build the thing."}]

    class _FakeMemory:
        short_term = None

    memory = None


def make_fake_agent(canned_response: str) -> FakeAgent:
    agent = FakeAgent(canned_response)
    agent.memory = FakeAgent._FakeMemory()
    agent.memory.short_term = FakeAgent._FakeShortTerm()
    return agent


def check(label: str, condition: bool) -> None:
    mark = "✅" if condition else "❌"
    print(f"{mark} {label}")
    assert condition, f"FAILED: {label}"


def expect_blocked(label: str, fn) -> None:
    try:
        fn()
        check(label, False)
    except RuntimeError as e:
        check(f"{label} ({e})", True)


def main():
    pipeline = TaskPipeline("Build a thing")
    # Patch out real API calls; keep the real guard/transition logic.
    pipeline._new_agent = lambda stage, prompt: make_fake_agent(_CANNED.get(stage, "ok"))

    print("\n=== 1. Can't skip planning: execution/validation/done from idle ===")
    expect_blocked("idle -> run_execution blocked", lambda: pipeline.run_execution())
    expect_blocked("idle -> run_validation blocked", lambda: pipeline.run_validation())
    expect_blocked("idle -> run_done blocked", lambda: pipeline.run_done())
    check("stage still idle", pipeline.stage == "idle")

    print("\n=== 2. Legal: idle -> planning ===")
    pipeline.start_planning()
    check("stage is planning", pipeline.stage == "planning")

    print("\n=== 3. Can't skip execution: planning -> validation/done blocked ===")
    expect_blocked("planning -> run_validation blocked (no structure yet anyway)", lambda: pipeline.run_validation())
    expect_blocked("planning -> run_done blocked", lambda: pipeline.run_done())

    print("\n=== 4. Can't run execution before plan is finalized ===")
    # plan_text is still None here even though transition table would allow planning->execution
    expect_blocked("run_execution blocked: plan not finalized", lambda: pipeline.run_execution())

    pipeline.finalize_planning()
    check("planning agent discarded", pipeline.planning_agent is None)
    check("plan captured", pipeline.plan_text is not None)

    print("\n=== 5. Can't chat with a discarded planning agent ===")
    expect_blocked("chat_planning blocked after finalize", lambda: pipeline.chat_planning("anything"))

    print("\n=== 6. Legal: planning -> execution (plan approved) ===")
    pipeline.run_execution()
    check("stage is execution", pipeline.stage == "execution")
    check("structure produced", pipeline.structure_text is not None)

    print("\n=== 7. Can't skip validation: execution -> done blocked ===")
    expect_blocked("execution -> run_done blocked", lambda: pipeline.run_done())
    check("stage still execution", pipeline.stage == "execution")

    print("\n=== 8. Validation round with functional issues but invariants OK ===")
    # This is the gap that existed before the fix: invariants_satisfied True alone used to be
    # enough to unlock done, even with RESULT: ISSUES (unrelated functional gaps).
    pipeline._new_agent = lambda stage, prompt: make_fake_agent(
        "Some checklist...\n[RESULT: ISSUES]\n[INVARIANTS: OK]"
    )
    response, metrics, is_valid = pipeline.run_validation()
    check("validation reports invalid (functional issues)", is_valid is False)
    check("invariants_satisfied is True (the trap)", pipeline.invariants_satisfied is True)
    check("validation_passed is False despite invariants OK", pipeline.validation_passed is False)

    print("\n=== 9. done blocked even though invariants_satisfied == True (the actual gap) ===")
    expect_blocked("run_done blocked: validation_passed is False, not just invariants", lambda: pipeline.run_done())

    print("\n=== 10. Can't re-validate the same unfixed structure (must go through execution again) ===")
    expect_blocked("validation -> run_validation again blocked", lambda: pipeline.run_validation())

    print("\n=== 11. Correction loop: validation -> execution -> validation -> done ===")
    pipeline._new_agent = lambda stage, prompt: make_fake_agent("Corrected structure")
    pipeline.run_execution(corrections=pipeline.validation_text)
    check("stage is execution again", pipeline.stage == "execution")
    check("validation_passed reset to False on new structure", pipeline.validation_passed is False)

    pipeline._new_agent = lambda stage, prompt: make_fake_agent(
        "All good.\n[RESULT: VALID]\n[INVARIANTS: OK]"
    )
    response, metrics, is_valid = pipeline.run_validation()
    check("second round validates clean", is_valid is True)
    check("validation_passed True for this exact structure", pipeline.validation_passed is True)

    pipeline._new_agent = lambda stage, prompt: make_fake_agent("Summary.")
    pipeline.run_done()
    check("stage is done", pipeline.stage == "done")

    print("\n=== 12. Can't jump past done ===")
    expect_blocked("done -> run_done again blocked", lambda: pipeline.run_done())
    expect_blocked("done -> run_execution blocked (must go via validation)", lambda: pipeline.run_execution())

    print("\n=== 13. reopen: done -> planning, with prior plan/structure handed as context ===")
    old_plan, old_structure, old_epoch = pipeline.plan_text, pipeline.structure_text, pipeline.epoch
    captured_handoff = {}

    def _capture_and_respond(text):
        captured_handoff["text"] = text
        return "Revised plan.\n[INVARIANTS_SET][/INVARIANTS_SET]", {"total_tokens": 0}

    def fake_new_agent_capture(stage, prompt):
        agent = make_fake_agent("Revised plan.\n[INVARIANTS_SET][/INVARIANTS_SET]")
        agent.send_message = _capture_and_respond
        return agent

    pipeline._new_agent = fake_new_agent_capture
    response, metrics = pipeline.reopen_planning("Add a dark mode toggle")
    check("stage back to planning", pipeline.stage == "planning")
    check("epoch bumped (fresh memory dirs, no reload of old planning agent)", pipeline.epoch == old_epoch + 1)
    check("old plan text handed to new planning agent", old_plan in captured_handoff["text"])
    check("old structure text handed to new planning agent", old_structure in captured_handoff["text"])
    check("revision request handed to new planning agent", "dark mode toggle" in captured_handoff["text"])
    check("plan_text cleared until /ready re-finalizes it", pipeline.plan_text is None)
    check("structure_text cleared (stale, belongs to pre-revision round)", pipeline.structure_text is None)
    check("validation_passed reset", pipeline.validation_passed is False)

    print("\n=== 14. Can't reopen from anywhere except done ===")
    expect_blocked("planning -> reopen_planning blocked", lambda: pipeline.reopen_planning())

    print("\n=== Transition table (shared with agent.py) ===")
    for state, allowed in ALLOWED_TRANSITIONS.items():
        print(f"  {state} -> {sorted(allowed)}")

    print("\n✅ All pipeline transition guard checks passed.")


_CANNED = {
    "planning": "FAKE PLAN: build the thing.\n[INVARIANTS_SET][/INVARIANTS_SET]",
    "execution": "FAKE STRUCTURE: src/, tests/",
    "validation": "Checklist...\n[RESULT: VALID]\n[INVARIANTS: OK]",
    "done": "Done. Summary.",
}


if __name__ == "__main__":
    main()
