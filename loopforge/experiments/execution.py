"""Isolated execution adapters for real candidate replays."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import time
from typing import Any, Protocol

from loopforge.experiments.models import ExperimentCandidate, ExperimentCase


@dataclass(frozen=True)
class ExecutionResult:
    candidate_id: str
    case_id: str
    status: str
    output: dict[str, Any]
    trace: dict[str, Any]
    metrics: dict[str, float]
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


class ExecutionAdapter(Protocol):
    adapter_id: str

    def execute(
        self,
        root: Path,
        candidate: ExperimentCandidate,
        case: ExperimentCase,
    ) -> ExecutionResult:
        """Execute one case against an isolated candidate harness."""


@dataclass(frozen=True)
class CommandExecutionAdapter:
    """Run a customer-provided replay command in an isolated repository copy.

    The command receives the case JSON on stdin and must print one JSON object
    containing `output`, `trace`, and optional `metrics` fields on stdout.
    """

    command: str
    timeout_seconds: float = 120.0
    adapter_id: str = "command-execution-v1"

    def execute(
        self,
        root: Path,
        candidate: ExperimentCandidate,
        case: ExperimentCase,
    ) -> ExecutionResult:
        started = time.monotonic()
        try:
            with tempfile.TemporaryDirectory(prefix="loopforge-search-") as directory:
                sandbox = Path(directory) / "repo"
                shutil.copytree(
                    root,
                    sandbox,
                    ignore=shutil.ignore_patterns(
                        ".git", ".loopforge", "__pycache__", ".pytest_cache", ".env", ".env.*"
                    ),
                )
                apply_file_updates(sandbox, candidate.file_updates)
                environment = {
                    "PATH": os.environ.get("PATH", ""),
                    "HOME": str(sandbox),
                    "TMPDIR": directory,
                    "LOOPFORGE_REPLAY_MODE": "isolated",
                    "LOOPFORGE_DISABLE_SIDE_EFFECTS": "1",
                }
                completed = subprocess.run(
                    shlex.split(self.command),
                    cwd=sandbox,
                    input=json.dumps(case.payload),
                    text=True,
                    capture_output=True,
                    timeout=self.timeout_seconds,
                    check=False,
                    env=environment,
                )
                elapsed_ms = (time.monotonic() - started) * 1000
                if completed.returncode != 0:
                    return ExecutionResult(
                        candidate_id=candidate.candidate_id,
                        case_id=case.case_id,
                        status="error",
                        output={},
                        trace={},
                        metrics={"latency_ms": elapsed_ms},
                        error=completed.stderr[-4000:] or f"exit code {completed.returncode}",
                    )
                payload = json.loads(completed.stdout)
                sandbox_claim = payload.get("sandbox") or {}
                if sandbox_claim.get("side_effects_virtualized") is not True:
                    return ExecutionResult(
                        candidate_id=candidate.candidate_id,
                        case_id=case.case_id,
                        status="error",
                        output={},
                        trace=dict(payload.get("trace") or {}),
                        metrics={"latency_ms": elapsed_ms},
                        error="replay command did not attest that side effects were virtualized",
                        metadata={"adapter_id": self.adapter_id},
                    )
                metrics = {key: float(value) for key, value in (payload.get("metrics") or {}).items()}
                metrics.setdefault("latency_ms", elapsed_ms)
                return ExecutionResult(
                    candidate_id=candidate.candidate_id,
                    case_id=case.case_id,
                    status="completed",
                    output=dict(payload.get("output") or {}),
                    trace=dict(payload.get("trace") or {}),
                    metrics=metrics,
                    metadata={"adapter_id": self.adapter_id},
                )
        except Exception as exc:
            return ExecutionResult(
                candidate_id=candidate.candidate_id,
                case_id=case.case_id,
                status="error",
                output={},
                trace={},
                metrics={"latency_ms": (time.monotonic() - started) * 1000},
                error=str(exc),
                metadata={"adapter_id": self.adapter_id},
            )


def validate_file_updates(root: Path, updates: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    resolved_root = root.resolve()
    seen: set[str] = set()
    for update in updates:
        relative = str(update.get("path") or "")
        if not relative or relative in seen:
            errors.append(f"missing or duplicate update path: {relative or '<empty>'}")
            continue
        seen.add(relative)
        path = (root / relative).resolve()
        if not path.is_relative_to(resolved_root):
            errors.append(f"path escapes repository: {relative}")
            continue
        parts = Path(relative).parts
        if any(part in {".git", ".loopforge"} for part in parts):
            errors.append(f"protected path cannot be changed: {relative}")
        if "content" not in update or not isinstance(update["content"], str):
            errors.append(f"file update requires text content: {relative}")
        if path.exists() and path.is_symlink():
            errors.append(f"symbolic links cannot be updated: {relative}")
        if not path.exists() and not relative.startswith(("harness/", "evals/")):
            errors.append(f"new files are limited to harness/ or evals/: {relative}")
        expected = str(update.get("expected_sha256") or "")
        if path.is_file() and expected:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != expected:
                errors.append(f"source fingerprint changed: {relative}")
    return errors


def apply_file_updates(root: Path, updates: list[dict[str, Any]]) -> None:
    errors = validate_file_updates(root, updates)
    if errors:
        raise ValueError("; ".join(errors))
    for update in updates:
        path = root / str(update["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(update["content"]), encoding="utf-8")
