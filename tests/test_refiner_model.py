from __future__ import annotations

from pathlib import Path

from loopforge.adapters.jsonl import JsonlTraceAdapter
from loopforge.discovery.scanner import discover_harness_artifacts
from loopforge.issues.miner import mine_issues
from loopforge.refinements.model import LocalProbabilisticRefinerModel
from loopforge.refinements.refiner import REFINER_PASSES
from loopforge.trajectories.builder import build_trajectory


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "support-agent"


def test_local_probabilistic_refiner_scores_ranked_candidates() -> None:
    traces = JsonlTraceAdapter("../traces/support-agent-cancellation.jsonl").read(FIXTURE_ROOT)
    trajectories = [build_trajectory(trace) for trace in traces]
    artifacts = discover_harness_artifacts(FIXTURE_ROOT)
    issue = mine_issues(traces, trajectories, artifacts)[0]

    candidates = LocalProbabilisticRefinerModel().score_passes(
        issue,
        [
            {
                "name": refiner_pass.name,
                "component_type": refiner_pass.component_type,
                "layer": refiner_pass.layer,
                "risk": refiner_pass.risk,
            }
            for refiner_pass in REFINER_PASSES
        ],
    )

    assert candidates[0].layer == "tool_description"
    assert candidates[0].score > candidates[-1].score
    assert candidates[0].evidence["evidence_trace_count"] == len(issue.evidence_trace_ids)
    assert "issue_confidence" in candidates[0].rationale
