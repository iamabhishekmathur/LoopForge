from __future__ import annotations

import runpy
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_langgraph_runtime_example_executes() -> None:
    namespace = runpy.run_path(str(REPO_ROOT / "examples" / "langgraph_runtime.py"))

    result = namespace["invoke_graph"]("Cancel my subscription", "trace-1")

    assert result["metadata_for_tracer"]["framework"] == "langgraph"
    assert result["metadata_for_tracer"]["runtime_manifest_id"].startswith("runtime-")


def test_openai_agents_runtime_example_executes() -> None:
    namespace = runpy.run_path(str(REPO_ROOT / "examples" / "openai_agents_runtime.py"))

    result = namespace["run_agent"]("Refund me", "trace-1")

    assert result["trace_metadata"]["framework"] == "openai-agents"
    assert result["trace_metadata"]["runtime_manifest_id"].startswith("runtime-")
