from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from loopforge.judging.behavior_map import build_behavior_map
from loopforge.judging.interpreter import interpret_trace
from loopforge.judging.planner import plan_judges
from loopforge.models.harness import HarnessArtifact
from loopforge.models.trace import Trace


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


def test_interpreter_scores_full_agent_trace_as_more_judgeable() -> None:
    trace = Trace.from_dict(
        {
            "schema_version": "1",
            "trace_id": "tr_full",
            "started_at": "2026-09-21T00:00:00Z",
            "inputs": {"user_message": "What plans can I downgrade to?"},
            "outputs": {"assistant_message": "Here are the downgrade options."},
            "spans": [
                {
                    "span_id": "sp_1",
                    "type": "tool_call",
                    "name": "get_plan_options",
                    "started_at": "2026-09-21T00:00:01Z",
                    "input": {"customer_id": "hash_1"},
                    "output": {"plans": ["basic", "pro"]},
                    "side_effect_class": "read",
                }
            ],
        }
    )

    observed = interpret_trace(trace)

    assert observed.user_intent == "What plans can I downgrade to?"
    assert observed.final_response == "Here are the downgrade options."
    assert observed.tool_calls == ["get_plan_options"]
    assert observed.judgeability_score >= 0.5
    assert "user_intent" in observed.available_evidence
    assert "final_response" in observed.available_evidence


def test_judge_planner_names_missing_evidence_for_partial_trace() -> None:
    trace = Trace.from_dict(
        {
            "schema_version": "1",
            "trace_id": "tr_sql_only",
            "started_at": "2026-09-21T00:00:00Z",
            "inputs": {"db_query": "select count(*) from orders"},
            "outputs": {"rowsCount": 1},
            "spans": [
                {
                    "span_id": "sp_1",
                    "type": "router",
                    "name": "sql_execution",
                    "started_at": "2026-09-21T00:00:01Z",
                    "input": {"db_query": "select count(*) from orders"},
                    "output": {"rowsCount": 1},
                }
            ],
        }
    )
    artifact = HarnessArtifact(
        artifact_id="system_1",
        artifact_type="system_prompt",
        path="harness/system.md",
        confidence=0.9,
        last_indexed_at="2026-09-21T00:00:00Z",
        summary="System-level agent instructions.",
    )
    behavior_map = build_behavior_map([artifact])

    observed = interpret_trace(trace)
    plan = plan_judges(observed, behavior_map)

    assert observed.user_intent is None
    assert "user_intent" in observed.missing_evidence
    assert "final_response" in observed.missing_evidence
    assert any(not task.judgeable for task in plan.tasks)


def test_judge_cli_persists_hypothesis_findings(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "harness").mkdir()
    (project / "traces").mkdir()
    (project / "harness" / "system.md").write_text(
        "You are a support agent. Use tools only when they answer the user's request.",
        encoding="utf-8",
    )
    trace = {
        "schema_version": "1",
        "trace_id": "tr_partial",
        "started_at": "2026-09-21T00:00:00Z",
        "inputs": {"db_query": "select count(*) from orders"},
        "outputs": {"rowsCount": 1},
        "spans": [
            {
                "span_id": "sp_1",
                "type": "router",
                "name": "sql_execution",
                "started_at": "2026-09-21T00:00:01Z",
                "input": {"db_query": "select count(*) from orders"},
                "output": {"rowsCount": 1},
            }
        ],
    }
    (project / "traces" / "sample.jsonl").write_text(json.dumps(trace) + "\n", encoding="utf-8")

    init = run_loopforge(["init", "--trace-path", "traces/*.jsonl"], project)
    shadow = run_loopforge(["shadow"], project)
    judge = run_loopforge(["judge", "run"], project)
    findings = run_loopforge(["judge", "list"], project)

    assert init.returncode == 0, init.stderr
    assert shadow.returncode == 0, shadow.stderr
    assert judge.returncode == 0, judge.stderr
    assert "findings: 1" in judge.stdout
    assert findings.returncode == 0, findings.stderr
    assert "insufficient_trace_coverage" in findings.stdout

