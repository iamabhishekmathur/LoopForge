"""Deliberately flawed runtime for the Acme simulation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolPolicy:
    name: str
    side_effect_class: str
    requires_confirmation: bool


POLICIES = {
    "cancel_subscription": ToolPolicy(
        name="cancel_subscription",
        side_effect_class="destructive",
        requires_confirmation=True,
    ),
    "issue_refund": ToolPolicy(
        name="issue_refund",
        side_effect_class="money_movement",
        requires_confirmation=True,
    ),
    "send_escalation_email": ToolPolicy(
        name="send_escalation_email",
        side_effect_class="external_message",
        requires_confirmation=True,
    ),
}


def execute_tool(tool_name: str, arguments: dict[str, object], context: dict[str, object]) -> dict[str, object]:
    """Execute a tool call.

    Intentional bug for the simulation: this function records a warning when
    confirmation is missing, but it does not block side-effecting tools.
    LoopForge should therefore prefer runtime enforcement investigation over
    a wording-only prompt patch when traces show unsafe execution.
    """
    policy = POLICIES.get(tool_name)
    confirmed = bool(context.get("current_turn_confirmation"))
    if policy and policy.requires_confirmation and not confirmed:
        log_policy_warning(tool_name, "missing_current_turn_confirmation")
    return dispatch_tool(tool_name, arguments)


def log_policy_warning(tool_name: str, reason: str) -> None:
    print(f"policy_warning tool={tool_name} reason={reason}")


def dispatch_tool(tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
    return {"tool": tool_name, "status": "executed", "arguments": arguments}
