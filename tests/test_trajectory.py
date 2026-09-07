from __future__ import annotations

from pathlib import Path

from loopforge.adapters.jsonl import JsonlTraceAdapter
from loopforge.trajectories.builder import build_trajectory


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "support-agent"


def test_trajectory_extracts_side_effect_and_feedback_signals() -> None:
    trace = JsonlTraceAdapter("../traces/support-agent-cancellation.jsonl").read(FIXTURE_ROOT)[0]

    trajectory = build_trajectory(trace)

    assert trajectory.trace_id == "tr_fail_001"
    assert trajectory.tool_calls == ["cancel_subscription"]
    assert "destructive" in trajectory.side_effect_classes
    assert "side_effect_destructive" in trajectory.signals
    assert "negative_feedback" in trajectory.signals
    assert trajectory.evidence_span_ids == ["sp_001_2"]
