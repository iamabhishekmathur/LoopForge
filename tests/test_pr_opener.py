from __future__ import annotations

from pathlib import Path

import pytest

from loopforge.models.patch import PatchBundle
from loopforge.models.pr import PullRequestArtifact
from loopforge.prs.opener import CommandResult, PrOpenError, open_pull_request


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], str | None]] = []

    def run(
        self,
        args: list[str],
        cwd: Path,
        input_text: str | None = None,
    ) -> CommandResult:
        self.calls.append((args, input_text))
        if args == ["git", "status", "--porcelain"]:
            return CommandResult(stdout="")
        if args == ["git", "rev-parse", "--abbrev-ref", "HEAD"]:
            return CommandResult(stdout="main\n")
        if args == ["git", "rev-parse", "HEAD"]:
            return CommandResult(stdout="abc123\n")
        if args[0:3] == ["gh", "pr", "create"]:
            return CommandResult(stdout="https://github.com/acme/agent/pull/7\n")
        return CommandResult()


def test_open_pull_request_runs_gated_git_and_github_sequence(tmp_path: Path) -> None:
    (tmp_path / "loopforge.yaml").write_text(
        "monitor:\n  open_prs: true\n  max_prs_per_day: 3\n",
        encoding="utf-8",
    )
    patch = PatchBundle(
        patch_id="PATCH-0001",
        issue_id="ISSUE-0001",
        target_artifacts=[
            {
                "artifact_id": "ART-0001",
                "artifact_type": "tool_definition",
                "path": "harness/tools/cancel_subscription.yaml",
                "confidence": 0.9,
            }
        ],
        diff="--- harness/tools/cancel_subscription.yaml\n+++ harness/tools/cancel_subscription.yaml\n",
        new_eval_ids=["EVAL-0001"],
        risk_assessment="Low risk.",
        rollback_plan="Revert the change.",
        status="gated",
    )
    pr = PullRequestArtifact(
        pr_id="PR-PATCH-0001",
        patch_id="PATCH-0001",
        issue_id="ISSUE-0001",
        title="Fix cancellation authorization",
        body="Reviewed gate context.",
        branch_name="loopforge/issue-0001/cancel-subscription",
        metadata={"requires_human_approval": True},
    )
    runner = FakeRunner()

    opened = open_pull_request(tmp_path, pr, patch, runner=runner)

    assert opened.url == "https://github.com/acme/agent/pull/7"
    assert opened.base_branch == "main"
    assert opened.commit_sha == "abc123"
    assert runner.calls == [
        (["git", "status", "--porcelain"], None),
        (["git", "apply", "--check"], patch.diff),
        (["gh", "auth", "status"], None),
        (["git", "rev-parse", "--abbrev-ref", "HEAD"], None),
        (["git", "checkout", "-b", "loopforge/issue-0001/cancel-subscription"], None),
        (["git", "apply", "--whitespace=nowarn"], patch.diff),
        (["git", "add", "harness/tools/cancel_subscription.yaml"], None),
        (["git", "commit", "-m", "Fix cancellation authorization"], None),
        (["git", "rev-parse", "HEAD"], None),
        (["git", "push", "-u", "origin", "loopforge/issue-0001/cancel-subscription"], None),
        (
            [
                "gh",
                "pr",
                "create",
                "--title",
                "Fix cancellation authorization",
                "--body",
                "Reviewed gate context.",
                "--base",
                "main",
                "--head",
                "loopforge/issue-0001/cancel-subscription",
            ],
            None,
        ),
    ]


def test_open_pull_request_refuses_disabled_config(tmp_path: Path) -> None:
    (tmp_path / "loopforge.yaml").write_text(
        "monitor:\n  open_prs: false\n  max_prs_per_day: 3\n",
        encoding="utf-8",
    )
    patch = PatchBundle(
        patch_id="PATCH-0001",
        issue_id="ISSUE-0001",
        target_artifacts=[],
        diff="",
        new_eval_ids=[],
        risk_assessment="",
        rollback_plan="",
        status="gated",
    )
    pr = PullRequestArtifact(
        pr_id="PR-PATCH-0001",
        patch_id="PATCH-0001",
        issue_id="ISSUE-0001",
        title="Fix issue",
        body="Body",
        branch_name="loopforge/issue-0001/patch",
        metadata={"requires_human_approval": True},
    )
    runner = FakeRunner()

    with pytest.raises(PrOpenError, match="open_prs is false"):
        open_pull_request(tmp_path, pr, patch, runner=runner)

    assert runner.calls == []
