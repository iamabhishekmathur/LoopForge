from __future__ import annotations

from pathlib import Path

from loopforge.adapters.jsonl import JsonlTraceAdapter
from loopforge.analysis.authorization import diagnose_action_authorization
from loopforge.trajectories.builder import build_trajectory


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "support-agent"


def test_authorization_diagnosis_scores_fixture_failures_probabilistically() -> None:
    traces = JsonlTraceAdapter("../traces/support-agent-cancellation.jsonl").read(FIXTURE_ROOT)
    trajectories = [build_trajectory(trace) for trace in traces]

    diagnosis = diagnose_action_authorization(traces, trajectories)

    assert diagnosis is not None
    assert diagnosis.ontology_id == "ACTION_AUTHORIZATION_ERROR"
    assert diagnosis.confidence > 0.7
    assert diagnosis.trace_observability == "high"
    assert diagnosis.implicated_tools == ["cancel_subscription"]
    assert diagnosis.calibration["scorer"] == "structured_probabilistic_v1"
    assert diagnosis.calibration["observable_from_traces"] is True
    assert {score.trace_id for score in diagnosis.trace_scores} == {
        "tr_fail_001",
        "tr_fail_002",
        "tr_fail_003",
        "tr_fail_004",
        "tr_fail_005",
    }


def test_authorization_diagnosis_ignores_clean_fixture_traces() -> None:
    traces = JsonlTraceAdapter("../traces/support-agent-cancellation.jsonl").read(FIXTURE_ROOT)
    clean_traces = [trace for trace in traces if trace.trace_id.startswith("tr_clean")]
    trajectories = [build_trajectory(trace) for trace in clean_traces]

    diagnosis = diagnose_action_authorization(clean_traces, trajectories)

    assert diagnosis is None
