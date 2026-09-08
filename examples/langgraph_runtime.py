"""LangGraph-style LoopForge runtime metadata example.

This example is dependency-free: replace the fake graph call with your compiled
LangGraph app invocation and attach the returned metadata to your tracer spans.
"""

from loopforge.sdk import RuntimeEmitter


SYSTEM_PROMPT = "You are a support agent. Ask for confirmation before destructive actions."
CANCEL_TOOL_SCHEMA = '{"name":"cancel_subscription","arguments":{"customer_id":"string"}}'


emitter = RuntimeEmitter(
    agent_id="support-agent",
    agent_version="2026.09.08",
    model_provider="openai",
    model_name="gpt-5",
    system_prompt=SYSTEM_PROMPT,
    tool_schemas={"cancel_subscription": CANCEL_TOOL_SCHEMA},
    tool_side_effect_classes={"cancel_subscription": "destructive"},
)


def invoke_graph(user_input: str, trace_id: str) -> dict[str, object]:
    metadata = emitter.trace_metadata(trace_id)
    return {
        "messages": [{"role": "user", "content": user_input}],
        "metadata_for_tracer": {
            **metadata,
            "framework": "langgraph",
            "graph_node": "support_agent",
            "checkpoint_namespace": "support-agent-prod",
        },
    }


if __name__ == "__main__":
    print(invoke_graph("Cancel my subscription", "trace-langgraph-1"))
