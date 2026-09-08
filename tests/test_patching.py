from __future__ import annotations

from pathlib import Path
import shutil

from loopforge.adapters.jsonl import JsonlTraceAdapter
from loopforge.discovery.scanner import discover_harness_artifacts
from loopforge.evals.generator import generate_eval_for_issue
from loopforge.issues.miner import mine_issues
from loopforge.patching.generator import generate_patch_for_issue
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
    assert "explicitly confirmed" in patch.diff
    assert "harness/system.md" not in patch.diff


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
    assert patch.target_artifacts[0]["path"] == "harness/permissions.yaml"
    assert "-    requires_confirmation: false" in patch.diff
    assert "+    requires_confirmation: true" in patch.diff
