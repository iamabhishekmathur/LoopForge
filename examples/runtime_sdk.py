from loopforge.sdk import RuntimeEmitter


emitter = RuntimeEmitter(
    agent_id="support-agent",
    agent_version="2026.09.08",
    model_provider="openai",
    model_name="gpt-5",
    system_prompt="You are a careful support agent.",
    tool_schemas={
        "cancel_subscription": '{"customer_id": "string"}',
    },
    tool_side_effect_classes={
        "cancel_subscription": "destructive",
    },
)

trace_id = "trace-123"
metadata = emitter.trace_metadata(trace_id)
manifest = emitter.manifest(trace_id)

print(metadata)
print(manifest.to_dict()["manifest_id"])
