from __future__ import annotations

from pathlib import Path

from loopforge.adapters.jsonl import JsonlTraceAdapter
from loopforge.discovery.scanner import discover_harness_artifacts
from loopforge.evals.generator import generate_eval_for_issue
from loopforge.issues.miner import mine_issues
from loopforge.patching.generator import generate_patch_for_issue
from loopforge.replay.runner import run_replay
from loopforge.trajectories.builder import build_trajectory


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "support-agent"


def test_run_replay_passes_when_patch_addresses_generated_eval() -> None:
    traces = JsonlTraceAdapter("../traces/support-agent-cancellation.jsonl").read(FIXTURE_ROOT)
    trajectories = [build_trajectory(trace) for trace in traces]
    artifacts = discover_harness_artifacts(FIXTURE_ROOT)
    issue = mine_issues(traces, trajectories, artifacts)[0]
    generated = generate_eval_for_issue(issue, traces)
    assert generated is not None
    eval_example, _ = generated
    patch = generate_patch_for_issue(FIXTURE_ROOT, issue, [eval_example.eval_id])
    assert patch is not None

    report = run_replay(
        patch,
        issue.to_dict(),
        [eval_example.to_dict()],
        [trace.to_dict() for trace in traces],
    )

    assert report.status == "pass"
    assert report.passed_cases == 2
    assert report.failed_cases == 0
    assert report.metadata["engine"] == "assertion_simulation_v1"
