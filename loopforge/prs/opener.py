"""Open GitHub pull requests from gated local PR artifacts."""

from __future__ import annotations

from dataclasses import dataclass
import subprocess
from pathlib import Path
from typing import Protocol

from loopforge.config import configured_max_prs_per_day, configured_open_prs
from loopforge.models.patch import PatchBundle
from loopforge.models.pr import PullRequestArtifact


class PrOpenError(RuntimeError):
    """Raised when a PR artifact cannot be opened safely."""


@dataclass(frozen=True)
class CommandResult:
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0


class CommandRunner(Protocol):
    def run(
        self,
        args: list[str],
        cwd: Path,
        input_text: str | None = None,
    ) -> CommandResult:
        ...


class SubprocessCommandRunner:
    def run(
        self,
        args: list[str],
        cwd: Path,
        input_text: str | None = None,
    ) -> CommandResult:
        completed = subprocess.run(
            args,
            cwd=cwd,
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
        )
        return CommandResult(
            stdout=completed.stdout,
            stderr=completed.stderr,
            returncode=completed.returncode,
        )


@dataclass(frozen=True)
class OpenedPullRequest:
    pr_id: str
    branch_name: str
    base_branch: str
    commit_sha: str
    url: str


def open_pull_request(
    root: Path,
    pr: PullRequestArtifact,
    patch: PatchBundle,
    runner: CommandRunner | None = None,
) -> OpenedPullRequest:
    runner = runner or SubprocessCommandRunner()
    _preflight(root, pr, patch, runner)
    base_branch = _run(runner, ["git", "rev-parse", "--abbrev-ref", "HEAD"], root).stdout.strip()

    _run(runner, ["git", "checkout", "-b", pr.branch_name], root)
    _run(runner, ["git", "apply", "--whitespace=nowarn"], root, input_text=patch.diff)
    target_paths = _target_paths(patch)
    _run(runner, ["git", "add", *target_paths], root)
    _run(runner, ["git", "commit", "-m", pr.title], root)
    commit_sha = _run(runner, ["git", "rev-parse", "HEAD"], root).stdout.strip()
    _run(runner, ["git", "push", "-u", "origin", pr.branch_name], root)
    url = _run(
        runner,
        [
            "gh",
            "pr",
            "create",
            "--title",
            pr.title,
            "--body",
            pr.body,
            "--base",
            base_branch,
            "--head",
            pr.branch_name,
        ],
        root,
    ).stdout.strip()

    return OpenedPullRequest(
        pr_id=pr.pr_id,
        branch_name=pr.branch_name,
        base_branch=base_branch,
        commit_sha=commit_sha,
        url=url,
    )


def _preflight(
    root: Path,
    pr: PullRequestArtifact,
    patch: PatchBundle,
    runner: CommandRunner,
) -> None:
    if not configured_open_prs(root):
        raise PrOpenError("open_prs is false in loopforge.yaml")
    if configured_max_prs_per_day(root) < 1:
        raise PrOpenError("max_prs_per_day must be at least 1")
    if pr.status not in {"drafted", "failed"}:
        raise PrOpenError(f"PR artifact status is not openable: {pr.status}")
    if not pr.metadata.get("requires_human_approval"):
        raise PrOpenError("PR artifact must require human approval")
    if patch.status != "gated":
        raise PrOpenError(f"patch is not gated: {patch.patch_id}")
    if pr.patch_id != patch.patch_id:
        raise PrOpenError("PR artifact patch ID does not match patch bundle")

    dirty = _run(runner, ["git", "status", "--porcelain"], root).stdout.strip()
    if dirty:
        raise PrOpenError("working tree must be clean before opening a PR")

    _run(runner, ["git", "apply", "--check"], root, input_text=patch.diff)
    _run(runner, ["gh", "auth", "status"], root)


def _target_paths(patch: PatchBundle) -> list[str]:
    paths = [
        str(artifact["path"])
        for artifact in patch.target_artifacts
        if artifact.get("path")
    ]
    if not paths:
        raise PrOpenError("patch bundle has no target artifact paths")
    return paths


def _run(
    runner: CommandRunner,
    args: list[str],
    cwd: Path,
    input_text: str | None = None,
) -> CommandResult:
    result = runner.run(args, cwd, input_text=input_text)
    if result.returncode != 0:
        command = " ".join(args)
        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise PrOpenError(f"{command} failed: {detail}")
    return result
