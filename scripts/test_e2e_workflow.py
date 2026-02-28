import os
import sys
from datetime import datetime

# Ensure the root directory is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.agents.coordinator import coordinator_graph
from app.core.config import get_settings

TEST_SCENARIOS = [
    {
        "name": "General Communication (NLG)",
        "message": "Hi, how are you doing today?",
    },
    {
        "name": "Health Score Calculation (Phase 3 + ML + NLG)",
        "message": "What is my current financial health score?",
    },
    {
        "name": "What-If Simulation (Dual Forecast + Impact)",
        "message": "What if I spend 15000 on a new phone right now?",
    },
    {
        "name": "Auto-Savings (Phase 1 Stub/Deterministic)",
        "message": "Can I save some money this week?",
    },
    {
        "name": "Opportunity / Product Matching",
        "message": "Do you have any loan offers for me?",
    },
    {
        "name": "Compliance Guard - Blacklist Test",
        "message": "Is this investment 100% safe and guarantee returns?",
    },
]


def run_tests():
    settings = get_settings()

    print("=" * 80)
    print("E2E WORKFLOW TEST RUNNER")
    print("=" * 80)
    print(f"Time: {datetime.now().isoformat()}")
    print(f"Gemini API Key Configured: {'YES' if settings.gemini_api_key else 'NO'}")
    print(f"Ollama Base URL Configured: {settings.ollama_base_url}")
    print("=" * 80)

    log_file_path = "e2e_test_logs.md"

    with open(log_file_path, "w", encoding="utf-8") as f:
        f.write("# CareBank E2E Workflow Test Logs\n\n")
        f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(
            f"**Gemini Configured:** {'Yes' if settings.gemini_api_key else 'No'}\n\n"
        )

        for idx, scenario in enumerate(TEST_SCENARIOS, 1):
            user_id = f"test_user_{idx}"
            print(
                f"\n[{idx}/{len(TEST_SCENARIOS)}] Running Scenario: {scenario['name']}"
            )
            print(f"User Message: {scenario['message']}")

            f.write(f"## {idx}. {scenario['name']}\n")
            f.write(f"**User Message:** `{scenario['message']}`\n\n")

            # Initial State
            initial_state = {
                "user_id": user_id,
                "message": scenario["message"],
            }

            try:
                # Invoke Coordinator
                final_state = coordinator_graph.invoke(initial_state)

                intent = final_state.get("intent", "unknown")
                agent_used = final_state.get("agent_used", "unknown")
                response = final_state.get("agent_response", "No response")

                # Try to extract metadata if it was logged in audit_log
                audit = final_state.get("audit_log", [])
                audit[-1] if audit else {}

                print(f"  -> Intent: {intent}")
                print(f"  -> Agent Used: {agent_used}")

                # If CommunicationAgent, try to see provider from response or logs (in a real app we'd attach it to state.metadata)
                # Wait, for Phase 4 communication agent, the output metadata isn't strictly bubbled up to state root,
                # but we can see the response quality.

                f.write(f"**Intent Detected:** `{intent}`\n")
                f.write(f"**Agent Routed:** `{agent_used}`\n\n")
                f.write(f"### Response:\n> {response}\n\n")

                if "[REDACTED]" in response or "Disclaimer" in response:
                    f.write("*Compliance Guard Modifications Detected in Response*\n\n")
                    print("  -> Compliance Guard Triggered: YES")

                f.write("---\n")
                print("  -> SUCCESS")

            except Exception as e:
                print(f"  -> FAILED: {str(e)}")
                f.write(f"**ERROR:** `{str(e)}`\n\n---\n")

    print(f"\nAll tests complete. Detailed logs written to {log_file_path}")


if __name__ == "__main__":
    run_tests()
