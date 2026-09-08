from __future__ import annotations

import json

from loopforge.sdk import RuntimeEmitter, build_runtime_manifest, trace_metadata


def test_runtime_emitter_builds_manifest_and_trace_metadata(tmp_path) -> None:
    emitter = RuntimeEmitter(
        agent_id="support-agent",
        agent_version="1.2.3",
        model_provider="openai",
        model_name="gpt-5",
        system_prompt="You are careful.",
        tool_schemas={"cancel_subscription": '{"type":"object"}'},
        tool_side_effect_classes={"cancel_subscription": "destructive"},
    )

    manifest = emitter.manifest("trace-1")
    metadata = emitter.trace_metadata("trace-1")
    path = emitter.write_manifest(tmp_path / "manifest.json", "trace-1")

    assert manifest.manifest_id.startswith("runtime-")
    assert manifest.tool_side_effect_classes["cancel_subscription"] == "destructive"
    assert metadata["runtime_manifest_id"] == manifest.manifest_id
    assert json.loads(path.read_text(encoding="utf-8"))["manifest_id"] == manifest.manifest_id


def test_runtime_manifest_hashes_change_with_prompt_content() -> None:
    first = build_runtime_manifest(
        trace_id="trace-1",
        agent_id="agent",
        agent_version="1",
        environment="prod",
        model_provider="openai",
        model_name="gpt-5",
        system_prompt="A",
    )
    second = build_runtime_manifest(
        trace_id="trace-1",
        agent_id="agent",
        agent_version="1",
        environment="prod",
        model_provider="openai",
        model_name="gpt-5",
        system_prompt="B",
    )

    assert first.system_prompt_hash != second.system_prompt_hash
    assert first.manifest_id != second.manifest_id
    assert trace_metadata(first)["agent_id"] == "agent"
