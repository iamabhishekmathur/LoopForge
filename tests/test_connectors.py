from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from loopforge.adapters.registry import (
    configured_trace_sources,
    connector_statuses,
    read_traces,
)
from loopforge.adapters.hosted import HostedTraceAdapter
from loopforge.adapters.sync import read_sync_state


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_loopforge(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "loopforge", *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def copy_fixture(tmp_path: Path) -> Path:
    fixture_root = tmp_path / "fixtures"
    shutil.copytree(
        REPO_ROOT / "fixtures",
        fixture_root,
        ignore=shutil.ignore_patterns(".loopforge"),
    )
    return fixture_root / "support-agent"


def test_configured_trace_sources_parse_multiple_sources(tmp_path: Path) -> None:
    (tmp_path / "loopforge.yaml").write_text(
        """
traces:
  sources:
    - id: local
      type: jsonl
      path: traces/*.jsonl
    - id: prod
      type: langsmith
      project: support-agent
""",
        encoding="utf-8",
    )

    sources = configured_trace_sources(tmp_path)

    assert [source.source_id for source in sources] == ["local", "prod"]
    assert sources[0].settings["path"] == "traces/*.jsonl"
    assert sources[1].source_type == "langsmith"
    assert sources[1].settings["project"] == "support-agent"


def test_connector_statuses_explain_hosted_connector_credentials(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    (tmp_path / "loopforge.yaml").write_text(
        "traces:\n  sources:\n    - id: prod\n      type: langsmith\n",
        encoding="utf-8",
    )

    statuses = connector_statuses(tmp_path)

    assert statuses[0].status == "needs_credentials"
    assert statuses[0].required_env == "LANGSMITH_API_KEY"


def test_read_traces_uses_all_jsonl_sources(tmp_path: Path) -> None:
    traces_dir = tmp_path / "traces"
    traces_dir.mkdir()
    trace = (
        '{"schema_version":"1","trace_id":"tr_1","started_at":"2026-01-01T00:00:00Z",'
        '"inputs":{},"spans":[{"span_id":"s1","type":"llm","name":"agent",'
        '"started_at":"2026-01-01T00:00:00Z"}]}\n'
    )
    (traces_dir / "a.jsonl").write_text(trace, encoding="utf-8")
    (tmp_path / "loopforge.yaml").write_text(
        "traces:\n  sources:\n    - id: local\n      type: jsonl\n      path: traces/*.jsonl\n",
        encoding="utf-8",
    )

    source_label, traces = read_traces(tmp_path)

    assert source_label == "local"
    assert [trace.trace_id for trace in traces] == ["tr_1"]
    state = read_sync_state(tmp_path, "local")
    assert state is not None
    assert state.trace_count == 1
    assert state.high_watermark_started_at == "2026-01-01T00:00:00Z"
    assert state.last_trace_id == "tr_1"


def test_connectors_cli_shows_fixture_source(tmp_path: Path) -> None:
    project_root = copy_fixture(tmp_path)

    list_result = run_loopforge(["connectors", "list"], project_root)
    doctor_result = run_loopforge(["connectors", "doctor"], project_root)

    assert list_result.returncode == 0
    assert "support-agent-jsonl" in list_result.stdout
    assert "ready" in list_result.stdout
    assert doctor_result.returncode == 0
    assert "ok" in doctor_result.stdout


def test_hosted_adapter_normalizes_langsmith_fixture() -> None:
    adapter = HostedTraceAdapter(
        "prod",
        "langsmith",
        {"fixture_path": "tests/fixtures/langsmith-runs.json"},
    )

    traces = adapter.read(REPO_ROOT)

    assert traces[0].trace_id == "prod:ls-run-1"
    assert traces[0].source_trace_id == "ls-run-1"
    assert traces[0].spans[0].type == "tool_call"
    assert traces[0].spans[0].name == "cancel_subscription"
    assert traces[0].spans[0].side_effect_class == "destructive"


def test_hosted_adapter_endpoint_includes_incremental_state() -> None:
    adapter = HostedTraceAdapter(
        "prod",
        "langsmith",
        {"base_url": "https://api.example.test", "project": "support-agent"},
        since="2026-01-01T00:00:00Z",
        cursor="abc",
    )

    endpoint = adapter._endpoint()

    assert endpoint.startswith("https://api.example.test/runs?")
    assert "project=support-agent" in endpoint
    assert "since=2026-01-01T00%3A00%3A00Z" in endpoint
    assert "cursor=abc" in endpoint


def test_hosted_adapter_normalizes_langfuse_fixture() -> None:
    adapter = HostedTraceAdapter(
        "prod",
        "langfuse",
        {"fixture_path": "tests/fixtures/langfuse-traces.json"},
    )

    traces = adapter.read(REPO_ROOT)

    assert traces[0].trace_id == "prod:lf-trace-1"
    assert traces[0].spans[0].type == "tool_call"
    assert traces[0].feedback[0]["value"] == 0


def test_hosted_adapter_normalizes_braintrust_fixture() -> None:
    adapter = HostedTraceAdapter(
        "prod",
        "braintrust",
        {"fixture_path": "tests/fixtures/braintrust-traces.json"},
    )

    traces = adapter.read(REPO_ROOT)

    assert traces[0].trace_id == "prod:bt-trace-1"
    assert traces[0].spans[0].type == "llm_call"
    assert traces[0].feedback == [{"type": "score", "value": 1}]


def test_hosted_adapter_normalizes_opentelemetry_fixture() -> None:
    adapter = HostedTraceAdapter(
        "prod",
        "opentelemetry",
        {"fixture_path": "tests/fixtures/otel-traces.json"},
    )

    traces = adapter.read(REPO_ROOT)

    assert traces[0].trace_id == "prod:otel-trace-1"
    assert traces[0].spans[0].type == "llm_call"


def test_read_traces_can_ingest_hosted_fixture_source(tmp_path: Path) -> None:
    (tmp_path / "loopforge.yaml").write_text(
        """
traces:
  sources:
    - id: prod
      type: langsmith
      fixture_path: fixture.json
""",
        encoding="utf-8",
    )
    (tmp_path / "fixture.json").write_text(
        (REPO_ROOT / "tests" / "fixtures" / "langsmith-runs.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )

    source_label, traces = read_traces(tmp_path)

    assert source_label == "prod"
    assert traces[0].trace_id == "prod:ls-run-1"
    state = read_sync_state(tmp_path, "prod")
    assert state is not None
    assert state.source_type == "langsmith"
    assert state.trace_count == 1
