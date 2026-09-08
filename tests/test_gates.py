from __future__ import annotations

from dataclasses import replace
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
    assert report.trust["replay_id"] == "REPLAY-PATCH-0001"
    assert report.trust["patch_concentration"] == "low"
    assert report.trust["refinement_scope"] == "workflow"
    assert report.trust["expected_outcome"]
    assert report.trust["validation_plan"]
    assert {suite["name"] for suite in report.suites} == {
        "patch_scope",
        "refinement_scope",
        "codebase_grounding",
        "artifact_fingerprint",
        "diagnosis_confidence",
        "eval_coverage",
        "expected_outcome",
        "diff_preview",
        "evaluator_validation",
        "replay_sandbox",
        "patch_concentration",
    }


def test_run_gates_warns_on_patch_concentration() -> None:
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
    operation_history = [
        {
            "operation_id": f"REFINE-prior-{index}",
            "artifact_path": "harness/tools/cancel_subscription.yaml",
            "metadata": {"post_merge_outcome": "no_effect"},
        }
        for index in range(3)
    ]

    report = run_gates(
        patch,
        issue.to_dict(),
        [eval_example.to_dict()],
        [validation.to_dict()],
        operation_history=operation_history,
    )

    concentration = [
        suite for suite in report.suites if suite["name"] == "patch_concentration"
    ][0]
    assert report.status == "warn"
    assert report.recommendation == "merge_after_human_review"
    assert report.trust["patch_concentration"] == "high"
    assert concentration["status"] == "warn"
    assert "unconfirmed refinement operations" in concentration["failed_cases"][0]


def test_run_gates_rejects_high_scope_without_reviewer_boundary() -> None:
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
    unsafe_patch = replace(
        patch,
        metadata={
            **patch.metadata,
            "refinement_scope": "org",
            "reviewer_boundary": "agent_team_review",
        },
    )

    report = run_gates(
        unsafe_patch,
        issue.to_dict(),
        [eval_example.to_dict()],
        [validation.to_dict()],
    )

    scope_suite = [suite for suite in report.suites if suite["name"] == "refinement_scope"][0]
    assert report.status == "reject"
    assert scope_suite["status"] == "reject"
    assert "org scope requires platform or security review" in scope_suite["failed_cases"]
