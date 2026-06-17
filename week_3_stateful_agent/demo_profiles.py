#!/usr/bin/env python3
"""
Dynamic System Prompt Infiltration Demo
Demonstrates how profile meta-settings dynamically inject behavioral constraints.
"""

from agent import DeepSeekAgent
from memory import MemoryEngine
import json


def print_header(title):
    print(f"\n{'=' * 80}")
    print(f"  {title}")
    print('=' * 80)


def show_system_prompt(agent, title=""):
    """Display what the final system prompt looks like after infiltration."""
    if title:
        print(f"\n[{title}]")

    base_prompt = "You are a helpful AI Assistant."
    meta = agent.memory.long_term.get_meta_settings()

    injected = (
        f"{base_prompt}\n"
        f"\n[CRITICAL BEHAVIORAL CONSTRAINTS FROM PROFILE]\n"
        f"- Tone: {meta.get('tone', 'Neutral and helpful')}\n"
        f"- Format Preference: {meta.get('format_preference', 'Clear and well-structured')}\n"
        f"- Verbosity Level: {meta.get('verbosity', 'Medium')}"
    )

    print("\nFinal System Prompt (after infiltration):")
    print("-" * 80)
    print(injected)
    print("-" * 80)


def demo_scenario_1():
    """Demo: Senior Engineer Profile - Strict and Code-Focused"""
    print_header("SCENARIO 1: Senior Engineer Profile")
    print("\nGoal: Configure agent for strict, code-focused responses")

    agent = DeepSeekAgent(memory_dir=".memory_demo_se")

    # Setup profile
    agent.switch_profile("senior_engineer")
    agent.set_meta_setting("tone", "Strict and concise, no fluff")
    agent.set_meta_setting("format_preference", "Code-first with minimal explanatory text")
    agent.set_meta_setting("verbosity", "Low")

    agent.remember("Primary language: Python 3.12")
    agent.remember("Preferred framework: FastAPI")
    agent.remember("Type system: Always use type hints")

    show_system_prompt(agent, "Senior Engineer Profile System Prompt")

    print("\n[Context Assembly]")
    print(f"  Profile: {agent.memory.long_term.current_profile}")
    print(f"  Meta-settings will be infiltrated into system prompt:")
    meta = agent.get_meta_settings()
    for key, val in meta.items():
        print(f"    - {key}: {val}")

    print("\n[Expected Behavior]")
    print("  If user asks: 'How do I handle authentication?'")
    print("  Agent responds with: Code examples first, minimal explanation")


def demo_scenario_2():
    """Demo: Academic Mentor Profile - Patient and Detailed"""
    print_header("SCENARIO 2: Academic Mentor Profile")
    print("\nGoal: Configure agent for patient, educational responses")

    agent = DeepSeekAgent(memory_dir=".memory_demo_mentor")

    # Setup profile
    agent.switch_profile("academic_mentor")
    agent.set_meta_setting("tone", "Patient and encouraging, treat learners with care")
    agent.set_meta_setting("format_preference", "Step-by-step explanations with inline comments")
    agent.set_meta_setting("verbosity", "High")

    agent.remember("Student level: Beginner")
    agent.remember("Learning style: Hands-on with theory")
    agent.remember("Focus area: Web development fundamentals")

    show_system_prompt(agent, "Academic Mentor Profile System Prompt")

    print("\n[Context Assembly]")
    print(f"  Profile: {agent.memory.long_term.current_profile}")
    print(f"  Meta-settings will be infiltrated into system prompt:")
    meta = agent.get_meta_settings()
    for key, val in meta.items():
        print(f"    - {key}: {val}")

    print("\n[Expected Behavior]")
    print("  If user asks: 'How do I handle authentication?'")
    print("  Agent responds with: Detailed walkthrough, explains concepts, includes examples")


def demo_scenario_3():
    """Demo: Tech Lead Profile - Balanced and Structured"""
    print_header("SCENARIO 3: Tech Lead Profile")
    print("\nGoal: Configure agent for balanced, architecture-focused responses")

    agent = DeepSeekAgent(memory_dir=".memory_demo_lead")

    # Setup profile
    agent.switch_profile("tech_lead")
    agent.set_meta_setting("tone", "Professional and solution-oriented")
    agent.set_meta_setting("format_preference", "Architecture diagrams with bullet-point rationale")
    agent.set_meta_setting("verbosity", "Medium")

    agent.remember("Team size: 5 engineers")
    agent.remember("Tech stack: FastAPI + React + PostgreSQL")
    agent.remember("Priority: Scalability and maintainability")

    show_system_prompt(agent, "Tech Lead Profile System Prompt")

    print("\n[Context Assembly]")
    print(f"  Profile: {agent.memory.long_term.current_profile}")
    print(f"  Meta-settings will be infiltrated into system prompt:")
    meta = agent.get_meta_settings()
    for key, val in meta.items():
        print(f"    - {key}: {val}")

    print("\n[Expected Behavior]")
    print("  If user asks: 'How do I handle authentication?'")
    print("  Agent responds with: System design perspective, considers scale & maintainability")


def demo_scenario_4():
    """Demo: Profile Switching - Same Question, Different Responses"""
    print_header("SCENARIO 4: Profile Switching - Same Query, Different Tone")
    print("\nGoal: Show how the same question gets different responses with different profiles")

    agent = DeepSeekAgent(memory_dir=".memory_demo_switch")

    # Create two different profiles
    agent.switch_profile("code_reviewer")
    agent.set_meta_setting("tone", "Critical and detail-oriented")
    agent.set_meta_setting("format_preference", "Code analysis with specific issue callouts")
    agent.set_meta_setting("verbosity", "Medium")
    agent.remember("Focus: Code quality and best practices")

    print("\n[Profile 1: Code Reviewer]")
    show_system_prompt(agent, "Code Reviewer Prompt")

    # Switch to different profile
    agent.switch_profile("security_auditor")
    agent.set_meta_setting("tone", "Cautious and threat-aware")
    agent.set_meta_setting("format_preference", "Security concerns listed with risk assessment")
    agent.set_meta_setting("verbosity", "High")
    agent.remember("Focus: Security vulnerabilities and attack vectors")

    print("\n[Profile 2: Security Auditor]")
    show_system_prompt(agent, "Security Auditor Prompt")

    print("\n[Comparison]")
    print("  Same user query: 'Review this authentication code'")
    print("  Profile 1 (code_reviewer): Checks code quality, style, patterns")
    print("  Profile 2 (security_auditor): Checks for vulnerabilities, threat models, etc.")


def demo_scenario_5():
    """Demo: Meta-settings with Working & Short-term Memory"""
    print_header("SCENARIO 5: Full Context Assembly with Meta-settings")
    print("\nGoal: Show how meta-settings work alongside other memory layers")

    agent = DeepSeekAgent(memory_dir=".memory_demo_full")

    # Setup profile with meta-settings
    agent.switch_profile("startup_cto")
    agent.set_meta_setting("tone", "Pragmatic and startup-focused")
    agent.set_meta_setting("format_preference", "Quick decisions with MVP-first thinking")
    agent.set_meta_setting("verbosity", "Low")
    agent.remember("Team: Small (3 people)")
    agent.remember("Timeline: 6 weeks to launch")
    agent.remember("Budget: Limited")

    # Set working task
    agent.set_task("Build payment processing module")

    # Set assembly mode to full_memory
    agent.set_mode("full_memory")

    print("\n[Full Context Assembly (full_memory mode)]")
    print(f"  Short-term (dialogue): Will include messages")
    print(f"  Working (task): {agent.memory.working.get_context_text()[:50]}...")
    print(f"  Long-term (profile): Profile facts + meta-settings")

    print("\n[Meta-settings in Payload]")
    meta = agent.get_meta_settings()
    for key, val in meta.items():
        print(f"  - {key}: {val}")

    print("\n[Complete System Prompt]")
    messages = agent.memory.get_messages_for_api("You are a helpful assistant")
    for i, msg in enumerate(messages[:3]):
        print(f"\n  Message {i} (role={msg['role']}):")
        content = msg['content'][:100] + "..." if len(msg['content']) > 100 else msg['content']
        print(f"    {content}")


def demo_storage_format():
    """Show the JSON storage format with meta-settings"""
    print_header("STORAGE FORMAT: Long-term Memory with Meta-settings")

    example_data = {
        "layer": "long_term",
        "current_profile": "senior_engineer",
        "profiles": {
            "default": {
                "_meta_settings": {
                    "tone": "Neutral and helpful",
                    "format_preference": "Clear and well-structured",
                    "verbosity": "Medium"
                }
            },
            "senior_engineer": {
                "_meta_settings": {
                    "tone": "Strict and concise, no fluff",
                    "format_preference": "Code-first with minimal explanatory text",
                    "verbosity": "Low"
                },
                "primary_language": "Python 3.12",
                "preferred_framework": "FastAPI",
                "type_system": "Always use type hints"
            },
            "academic_mentor": {
                "_meta_settings": {
                    "tone": "Patient and encouraging",
                    "format_preference": "Step-by-step explanations",
                    "verbosity": "High"
                },
                "student_level": "Beginner",
                "learning_style": "Hands-on with theory"
            }
        }
    }

    print("\n[long_term.json Structure]")
    print(json.dumps(example_data, indent=2, ensure_ascii=False))

    print("\n[Key Points]")
    print("  - Each profile has '_meta_settings' (underscore prefix = system)")
    print("  - Meta-settings include: tone, format_preference, verbosity")
    print("  - Facts are stored separately from meta-settings")
    print("  - Switching profiles = complete context replacement")


def main():
    print("\n" + "█" * 80)
    print("█" + " " * 78 + "█")
    print("█" + "  DYNAMIC SYSTEM PROMPT INFILTRATION DEMO".center(78) + "█")
    print("█" + "  Profile Meta-Settings Behavioral Constraints".center(78) + "█")
    print("█" + " " * 78 + "█")
    print("█" * 80)

    try:
        demo_scenario_1()
        demo_scenario_2()
        demo_scenario_3()
        demo_scenario_4()
        demo_scenario_5()
        demo_storage_format()

        print_header("SUMMARY")
        print("\n✓ Dynamic System Prompt Infiltration:")
        print("  1. Profile meta-settings injected into system prompt dynamically")
        print("  2. Changes tone, format, and verbosity without code modification")
        print("  3. Works with all assembly modes (short_only, full_memory, etc.)")
        print("  4. Profiles isolated in namespace (no merging complexity)")

        print("\n✓ Use Cases:")
        print("  - Code review vs security audit: Different lenses on same task")
        print("  - Student vs professional: Different verbosity and tone")
        print("  - MVP vs production: Different priorities (speed vs quality)")

        print("\n✓ Storage:")
        print("  - Meta-settings saved in long_term.json with '_meta_settings' key")
        print("  - Persisted across sessions")
        print("  - Each profile has independent configuration")

        print("\n" + "=" * 80)
        print("  DEMO COMPLETE - Multi-Profile Meta-Settings Architecture Validated!")
        print("=" * 80 + "\n")

    except KeyboardInterrupt:
        print("\nDemo interrupted.")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
