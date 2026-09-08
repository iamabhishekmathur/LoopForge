from __future__ import annotations

from pathlib import Path

from loopforge.adapters.jsonl import JsonlTraceAdapter
from loopforge.confirmation.runner import confirm_patch_outcome
from loopforge.discovery.scanner import discover_harness_artifacts
from loopforge.evals.generator import generate_eval_for_issue
from loopforge.issues.miner import mine_issues
from loopforge.refinements.refiner import refine_issue
from loopforge.trajectories.builder import build_trajectory


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "support-agent"


def _patch_issue_and_operations() -> tuple[object, dict[str, object], list[dict[str, object]]]:
    traces = JsonlTraceAdapter("../traces/support-agent-cancellation.jsonl").read(FIXTURE_ROOT)
    trajectories = [build_trajectory(trace) for trace in traces]
    artifacts = discover_harness_artifacts(FIXTURE_ROOT)
    issue = mine_issues(traces, trajectories, artifacts)[0]
    generated = generate_eval_for_issue(issue, traces)
    assert generated is not None
    eval_example, _ = generated
    draft = refine_issue(FIXTURE_ROOT, issue, [eval_example.eval_id])
    assert draft.patch is not None
    return draft.patch, issue.to_dict(), [operation.to_dict() for operation in draft.operations]


def test_confirm_patch_outcome_classifies_confirmed() -> None:
    patch, issue, operations = _patch_issue_and_operations()

    report = confirm_patch_outcome(
        patch,
        issue,
        operations,
        observed_trace_count=10,
        recurring_failure_count=0,
    )

    assert report.outcome == "confirmed"
    assert report.status == "complete"
    assert report.baseline_failure_rate == 1.0
    assert report.observed_failure_rate == 0.0
    assert report.operation_ids == ["REFINE-0001-0001"]


def test_confirm_patch_outcome_classifies_no_effect_and_insufficient_data() -> None:
    patch, issue, operations = _patch_issue_and_operations()

    no_effect = confirm_patch_outcome(
        patch,
        issue,
        operations,
        observed_trace_count=10,
        recurring_failure_count=8,
    )
    insufficient = confirm_patch_outcome(patch, issue, operations)

    assert no_effect.outcome == "no_effect"
    assert no_effect.recommendation == "revisit_patch_layer"
    assert insufficient.outcome == "insufficient_data"
    assert insufficient.recommendation == "continue_monitoring"
