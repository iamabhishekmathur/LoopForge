"""OpenAI Agents SDK-style LoopForge runtime metadata example.

This example is dependency-free: attach the metadata to your trace/span payloads
around Agent runs, tool calls, handoffs, and guardrail checks.
"""

from loopforge.sdk import RuntimeEmitter


INSTRUCTIONS = "You are a careful support agent. Confirm before external side effects."
REFUND_TOOL_SCHEMA = '{"name":"refund_customer","arguments":{"customer_id":"string","amount":"number"}}'


emitter = RuntimeEmitter(
    agent_id="support-agent",
    agent_version="2026.09.08",
    model_provider="openai",
    model_name="gpt-5",
    system_prompt=INSTRUCTIONS,
    tool_schemas={"refund_customer": REFUND_TOOL_SCHEMA},
    tool_side_effect_classes={"refund_customer": "financial"},
)


def run_agent(user_input: str, trace_id: str) -> dict[str, object]:
    metadata = emitter.trace_metadata(trace_id)
    return {
        "input": user_input,
        "trace_metadata": {
            **metadata,
            "framework": "openai-agents",
            "agent_name": "support-agent",
            "guardrails": ["side_effect_confirmation"],
        },
    }


if __name__ == "__main__":
    print(run_agent("Refund my last payment", "trace-openai-agents-1"))
