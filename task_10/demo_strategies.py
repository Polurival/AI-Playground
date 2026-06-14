"""
Demo script showing behavior of different context strategies.
This is a standalone educational demo (does not require API key).
"""

from strategies import (
    SlidingWindowStrategy,
    StickyFactsStrategy,
    BranchingStrategy
)


def demo_sliding_window():
    """Demonstrate sliding window behavior."""
    print("\n" + "=" * 60)
    print("DEMO: Sliding Window Strategy (window_size=4)")
    print("=" * 60)

    strategy = SlidingWindowStrategy(window_size=4)

    # Simulate 6 messages
    messages = [
        ("user", "We need a users table."),
        ("assistant", "I'll help you design the users table."),
        ("user", "Primary key should be UUID."),
        ("assistant", "UUID is a good choice for..."),
        ("user", "Add email and phone fields."),
        ("assistant", "Good additions. Email should be..."),
    ]

    for i, (role, content) in enumerate(messages, 1):
        strategy.add_message(role, content)
        print(f"\n[Turn {i}] Added: {role.upper()}")
        print(f"  Content: {content[:50]}...")
        print(f"  Messages in memory: {len(strategy.messages)}")

        if i > strategy.window_size:
            strategy.update_from_response("")
            print(f"  → Window limit exceeded. Trimming...")

    print("\n[Final State]")
    print(f"  Messages retained: {len(strategy.messages)}")
    for j, msg in enumerate(strategy.messages):
        print(f"    {j + 1}. [{msg['role'].upper()}] {msg['content'][:40]}...")

    print(f"\n  Note: First {len(messages) - strategy.window_size} messages are lost!")


def demo_sticky_facts():
    """Demonstrate sticky facts behavior."""
    print("\n" + "=" * 60)
    print("DEMO: Sticky Facts Strategy (window_size=4)")
    print("=" * 60)

    strategy = StickyFactsStrategy(window_size=4)

    # Simulate messages with manual fact extraction
    messages = [
        ("user", "We need a users table with UUID primary key."),
        ("assistant", "Great choice. UUID prevents collisions."),
        ("user", "Add email field. Should be unique."),
        ("assistant", "Email should have a unique constraint."),
        ("user", "Also track created_at timestamp."),
        ("assistant", "Timestamps are essential for auditing."),
    ]

    for i, (role, content) in enumerate(messages, 1):
        strategy.add_message(role, content)
        print(f"\n[Turn {i}] Added: {role.upper()}")
        print(f"  Content: {content[:50]}...")

        if role == "user" and i > 1:
            # Simulate fact extraction
            if "UUID" in content or i == 1:
                strategy.facts["primary_key"] = "UUID"
            if "email" in content.lower():
                strategy.facts["fields"] = strategy.facts.get("fields", []) + ["email"]
            if "timestamp" in content.lower():
                strategy.facts["fields"] = strategy.facts.get("fields", []) + ["created_at"]

            print(f"  Facts updated: {strategy.facts}")

    print("\n[Final State]")
    print(f"  Messages in window: {len(strategy.messages)} (window_size={strategy.window_size})")
    for j, msg in enumerate(strategy.messages):
        print(f"    {j + 1}. [{msg['role'].upper()}] {msg['content'][:40]}...")

    print(f"\n  Persistent Facts: {strategy.facts}")
    print(f"  → Early constraint (UUID) preserved externally!")


def demo_branching():
    """Demonstrate branching behavior."""
    print("\n" + "=" * 60)
    print("DEMO: Branching Strategy")
    print("=" * 60)

    strategy = BranchingStrategy(window_size=4)

    # Main branch conversation
    print("\n[Branch: main]")
    main_messages = [
        ("user", "Let's use UUID for the primary key."),
        ("assistant", "UUID is a good choice."),
        ("user", "Add email and phone fields."),
        ("assistant", "Both are useful fields."),
    ]

    for i, (role, content) in enumerate(main_messages, 1):
        strategy.add_message(role, content)
        print(f"  {i}. [{role.upper()}] {content[:40]}...")

    print(f"\n  Messages: {len(strategy.messages)}")

    # Create checkpoint and branch
    strategy.create_checkpoint("main_uuid_design")
    strategy.messages = []  # Simulate branch switch
    print("\n[Branch: alternative_design]")
    print("  (Starting fresh from checkpoint)")

    # Alternative branch conversation
    alt_messages = [
        ("user", "What if we use auto-increment instead?"),
        ("assistant", "Auto-increment is simpler but has limitations."),
        ("user", "That's true. Let's stick with UUID then."),
    ]

    for i, (role, content) in enumerate(alt_messages, 1):
        strategy.add_message(role, content)
        print(f"  {i}. [{role.upper()}] {content[:40]}...")

    print(f"\n  Messages: {len(strategy.messages)}")

    # List branches
    print(f"\n[Available Branches]")
    for branch_name in strategy.list_branches():
        msg_count = len(strategy.branches[branch_name])
        print(f"  - {branch_name}: {msg_count} messages")

    # Switch back
    print(f"\n[Switching back to: main_uuid_design]")
    strategy.switch_branch("main_uuid_design")
    print(f"  Restored {len(strategy.messages)} messages")
    for j, msg in enumerate(strategy.messages[:2]):
        print(f"    {j + 1}. [{msg['role'].upper()}] {msg['content'][:40]}...")


def demo_token_tracking():
    """Show token tracking capabilities."""
    print("\n" + "=" * 60)
    print("DEMO: Token Tracking & Debug Info")
    print("=" * 60)

    strategies = [
        ("Sliding Window", SlidingWindowStrategy(window_size=6)),
        ("Sticky Facts", StickyFactsStrategy(window_size=6)),
        ("Branching", BranchingStrategy(window_size=6)),
    ]

    # Add same messages to all strategies
    test_messages = [
        ("user", "What's the best way to structure a database?"),
        ("assistant", "It depends on your use case and scale."),
        ("user", "We expect 1M users and heavy analytics queries."),
    ]

    for name, strategy in strategies:
        print(f"\n[{name}]")
        for role, content in test_messages:
            strategy.add_message(role, content)

        debug = strategy.get_debug_info()
        print(f"  Debug Info:")
        for key, value in debug.items():
            if key != "strategy":
                print(f"    - {key}: {value}")


def main():
    """Run all demos."""
    print("\n" + "🎯 STRATEGY PATTERN DEMO - Educational Walkthrough")

    demo_sliding_window()
    demo_sticky_facts()
    demo_branching()
    demo_token_tracking()

    print("\n" + "=" * 60)
    print("DEMO COMPLETE")
    print("=" * 60)
    print("\nTo run the actual agent with API integration, use:")
    print("  python main.py")
    print()


if __name__ == "__main__":
    main()
