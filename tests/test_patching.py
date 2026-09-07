from __future__ import annotations

from pathlib import Path

from loopforge.adapters.jsonl import JsonlTraceAdapter
from loopforge.discovery.scanner import discover_harness_artifacts
from loopforge.evals.generator import generate_eval_for_issue
from loopforge.issues.miner import mine_issues
from loopforge.patching.generator import generate_patch_for_issue
from loopforge.trajectories.builder import build_trajectory


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "support-agent"


def test_generate_patch_for_grounded_authorization_issue() -> None:
    traces = JsonlTraceAdapter("../traces/support-agent-cancellation.jsonl").read(FIXTURE_ROOT)
    trajectories = [build_trajectory(trace) for trace in traces]
    artifacts = discover_harness_artifacts(FIXTURE_ROOT)
    issue = mine_issues(traces, trajectories, artifacts)[0]
    generated = generate_eval_for_issue(issue, traces)
    assert generated is not None
    eval_example, _ = generated

    patch = generate_patch_for_issue(FIXTURE_ROOT, issue, [eval_example.eval_id])

    assert patch is not None
    assert patch.patch_id == "PATCH-0001"
    assert patch.issue_id == "ISSUE-0001"
    assert patch.new_eval_ids == ["EVAL-0001"]
    assert patch.target_artifacts[0]["path"] == "harness/tools/cancel_subscription.yaml"
    assert "explicitly confirmed" in patch.diff
    assert "harness/system.md" not in patch.diff
