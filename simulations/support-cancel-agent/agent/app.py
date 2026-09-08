"""Tiny simulated agent implementation for LoopForge tests.

This is not meant to be a production agent. It documents the behavior that
produced the recorded observability traces in this simulation.
"""

from __future__ import annotations


def decide_tool(user_message: str) -> str | None:
    lowered = user_message.lower()
    if "cancel" in lowered:
        return "cancel_subscription"
    return None


def run_agent(user_message: str) -> dict[str, object]:
    tool = decide_tool(user_message)
    if tool is None:
        return {
            "assistant_message": "I can help with your subscription. What would you like to change?",
            "tool_calls": [],
        }
    return {
        "assistant_message": "Your subscription has been cancelled.",
        "tool_calls": [
            {
                "name": tool,
                "arguments": {"customer_id": "cust_simulated", "reason": "support_request"},
            }
        ],
    }
