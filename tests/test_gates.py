from __future__ import annotations

from pathlib import Path

from loopforge.adapters.jsonl import JsonlTraceAdapter
from loopforge.discovery.scanner import discover_harness_artifacts
from loopforge.evals.generator import generate_eval_for_issue
from loopforge.evals.validator import validate_evaluator
from loopforge.gates.runner import run_gates
from loopforge.issues.miner import mine_issues
from loopforge.patching.generator import generate_patch_for_issue
from loopforge.trajectories.builder import build_trajectory


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "support-agent"


def test_run_gates_accepts_grounded_patch_with_validated_eval() -> None:
    traces = JsonlTraceAdapter("../traces/support-agent-cancellation.jsonl").read(FIXTURE_ROOT)
    trajectories = [build_trajectory(trace) for trace in traces]
    artifacts = discover_harness_artifacts(FIXTURE_ROOT)
    issue = mine_issues(traces, trajectories, artifacts)[0]
    generated = generate_eval_for_issue(issue, traces)
    assert generated is not None
    eval_example, evaluator = generated
    validation = validate_evaluator(issue, evaluator, traces)
    patch = generate_patch_for_issue(FIXTURE_ROOT, issue, [eval_example.eval_id])
    assert patch is not None

    report = run_gates(
        patch,
        issue.to_dict(),
        [eval_example.to_dict()],
        [validation.to_dict()],
    )

    assert report.status == "pass"
    assert report.recommendation == "merge_after_human_review"
    assert report.trust["recommendation_quality_level"] == "gated_patch"
    assert report.trust["runtime_manifest_coverage"] == 1.0
    assert report.trust["diagnosis_confidence"] >= 0.7
    assert {suite["name"] for suite in report.suites} == {
        "patch_scope",
        "codebase_grounding",
        "artifact_fingerprint",
        "diagnosis_confidence",
        "eval_coverage",
        "evaluator_validation",
        "replay_sandbox",
    }
