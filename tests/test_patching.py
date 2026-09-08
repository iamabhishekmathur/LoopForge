from __future__ import annotations

from pathlib import Path
import shutil

from loopforge.adapters.jsonl import JsonlTraceAdapter
from loopforge.discovery.scanner import discover_harness_artifacts
from loopforge.evals.generator import generate_eval_for_issue
from loopforge.issues.miner import mine_issues
from loopforge.patching.generator import generate_patch_for_issue
from loopforge.refinements.ledger import refinement_operations_for_patch
from loopforge.refinements.refiner import refine_issue
from loopforge.replay.runner import run_replay
from loopforge.trajectories.builder import build_trajectory


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "support-agent"
REPO_ROOT = Path(__file__).resolve().parents[1]


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
    assert len(patch.target_artifacts[0]["sha256"]) == 64
    assert patch.metadata["diagnosis_confidence"] == issue.confidence
    assert patch.metadata["refinement_scope"] == "workflow"
    assert patch.metadata["expected_outcome"]
    assert patch.metadata["validation_plan"]
    assert "explicitly confirmed" in patch.diff
    assert "harness/system.md" not in patch.diff

    operations = refinement_operations_for_patch(
        issue,
        patch,
        created_at="2026-01-01T00:00:00+00:00",
    )
    assert len(operations) == 1
    operation = operations[0]
    assert operation.operation_id == "REFINE-0001-0001"
    assert operation.operation_type == "update"
    assert operation.component_type == "tool"
    assert operation.artifact_path == "harness/tools/cancel_subscription.yaml"
    assert operation.patch_id == "PATCH-0001"
    assert operation.source_trace_ids == issue.evidence_trace_ids
    assert operation.source_eval_ids == ["EVAL-0001"]
    assert operation.scope == "workflow"
    assert operation.expected_outcome == patch.metadata["expected_outcome"]
    assert operation.validation_plan == patch.metadata["validation_plan"]
    assert operation.rollback_plan == patch.rollback_plan
    assert operation.preview_diff == patch.diff
    assert operation.reviewer_boundary == "agent_team_review"
    assert operation.provenance["ai_observed"] is True
    assert operation.provenance["component_pass"] is None
    assert operation.provenance["requires_human_approval"] is True
    assert "additions" in operation.diff_summary

    draft = refine_issue(FIXTURE_ROOT, issue, [eval_example.eval_id])
    assert draft.status == "drafted"
    assert draft.selected_pass == "tool_refiner"
    assert draft.selected_layer == "tool_description"
    assert draft.patch is not None
    assert draft.patch.metadata["component_pass"] == "tool_refiner"
    assert draft.operations[0].provenance["component_pass"] == "tool_refiner"


def test_generate_permission_policy_patch_when_requested(tmp_path: Path) -> None:
    fixture_root = tmp_path / "fixtures"
    shutil.copytree(
        REPO_ROOT / "fixtures",
        fixture_root,
        ignore=shutil.ignore_patterns(".loopforge"),
    )
    project_root = fixture_root / "support-agent"
    permissions = project_root / "harness" / "permissions.yaml"
    permissions.write_text(
        "tools:\n  cancel_subscription:\n    requires_confirmation: false\n",
        encoding="utf-8",
    )
    traces = JsonlTraceAdapter("../traces/support-agent-cancellation.jsonl").read(project_root)
    trajectories = [build_trajectory(trace) for trace in traces]
    artifacts = discover_harness_artifacts(project_root)
    issue = mine_issues(traces, trajectories, artifacts)[0]
    generated = generate_eval_for_issue(issue, traces)
    assert generated is not None
    eval_example, _ = generated

    patch = generate_patch_for_issue(
        project_root,
        issue,
        [eval_example.eval_id],
        preferred_layer="permission_policy",
    )

    assert patch is not None
    assert patch.metadata["patch_layer"] == "permission_policy"
    assert patch.metadata["refinement_scope"] == "project"
    assert patch.metadata["reviewer_boundary"] == "security_review"
    assert patch.target_artifacts[0]["path"] == "harness/permissions.yaml"
    assert "-    requires_confirmation: false" in patch.diff
    assert "+    requires_confirmation: true" in patch.diff

    draft = refine_issue(
        project_root,
        issue,
        [eval_example.eval_id],
        preferred_layer="permission_policy",
    )
    assert draft.patch is not None
    assert draft.selected_pass == "policy_refiner"
    assert draft.patch.metadata["component_type"] == "policy"


def test_generate_subagent_spec_patch_when_requested() -> None:
    traces = JsonlTraceAdapter("../traces/support-agent-cancellation.jsonl").read(FIXTURE_ROOT)
    trajectories = [build_trajectory(trace) for trace in traces]
    artifacts = discover_harness_artifacts(FIXTURE_ROOT)
    issue = mine_issues(traces, trajectories, artifacts)[0]
    generated = generate_eval_for_issue(issue, traces)
    assert generated is not None
    eval_example, _ = generated

    patch = generate_patch_for_issue(
        FIXTURE_ROOT,
        issue,
        [eval_example.eval_id],
        preferred_layer="subagent_spec",
    )

    assert patch is not None
    assert patch.metadata["strategy"] == "subagent_spec_patch"
    assert patch.metadata["reviewer_boundary"] == "agent_architecture_review"
    assert patch.target_artifacts[0]["artifact_type"] == "sub_agent"
    assert patch.target_artifacts[0]["path"] == "harness/subagents/side_effect_reviewer.md"
    assert "Side Effect Reviewer" in patch.diff

    operations = refinement_operations_for_patch(
        issue,
        patch,
        created_at="2026-01-01T00:00:00+00:00",
    )
    assert operations[0].component_type == "sub_agent"
    assert operations[0].reviewer_boundary == "agent_architecture_review"


def test_generate_system_prompt_patch_when_requested() -> None:
    traces = JsonlTraceAdapter("../traces/support-agent-cancellation.jsonl").read(FIXTURE_ROOT)
    trajectories = [build_trajectory(trace) for trace in traces]
    artifacts = discover_harness_artifacts(FIXTURE_ROOT)
    issue = mine_issues(traces, trajectories, artifacts)[0]
    generated = generate_eval_for_issue(issue, traces)
    assert generated is not None
    eval_example, _ = generated

    patch = generate_patch_for_issue(
        FIXTURE_ROOT,
        issue,
        [eval_example.eval_id],
        preferred_layer="system_prompt",
    )
    assert patch is not None

    replay = run_replay(patch, issue.to_dict(), [eval_example.to_dict()])

    assert patch.metadata["patch_layer"] == "system_prompt"
    assert patch.target_artifacts[0]["path"] == "harness/system.md"
    assert "LoopForge guidance: ACTION_AUTHORIZATION_ERROR" in patch.diff
    assert replay.status == "pass"
