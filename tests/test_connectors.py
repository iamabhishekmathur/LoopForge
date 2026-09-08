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


def test_connectors_cli_shows_fixture_source(tmp_path: Path) -> None:
    project_root = copy_fixture(tmp_path)

    list_result = run_loopforge(["connectors", "list"], project_root)
    doctor_result = run_loopforge(["connectors", "doctor"], project_root)

    assert list_result.returncode == 0
    assert "support-agent-jsonl" in list_result.stdout
    assert "ready" in list_result.stdout
    assert doctor_result.returncode == 0
    assert "ok" in doctor_result.stdout
