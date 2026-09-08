"""Trace replay simulation for acceptance gates."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from loopforge.models.patch import PatchBundle
from loopforge.paths import LOCAL_DIR


@dataclass(frozen=True)
class ReplayReport:
    replay_id: str
    patch_id: str
    status: str
    passed_cases: int
    failed_cases: int
    cases: list[dict[str, Any]]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "replay_id": self.replay_id,
            "patch_id": self.patch_id,
            "status": self.status,
            "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases,
            "cases": self.cases,
            "metadata": self.metadata,
        }


def run_replay(
    patch: PatchBundle,
    issue: dict[str, Any],
    evals: list[dict[str, Any]],
    traces: list[dict[str, Any]] | None = None,
) -> ReplayReport:
    evidence_trace_ids = set(str(item) for item in issue.get("evidence_trace_ids", []))
    cases = []
    for eval_example in evals:
        assertions = eval_example.get("assertions", [])
        passed = _patch_addresses_assertions(patch, assertions)
        cases.append(
            {
                "eval_id": eval_example.get("eval_id"),
                "status": "pass" if passed else "fail",
                "source_trace_ids": eval_example.get("source_trace_ids", []),
                "assertions": assertions,
                "reason": "patch updates implicated harness contract"
                if passed
                else "patch does not address replay assertions",
            }
        )

    if traces:
        covered = {
            str(trace.get("trace_id"))
            for trace in traces
            if str(trace.get("trace_id")) in evidence_trace_ids
        }
        cases.append(
            {
                "eval_id": "evidence_trace_coverage",
                "status": "pass" if covered == evidence_trace_ids else "fail",
                "source_trace_ids": sorted(covered),
                "reason": "all evidence traces are available for replay"
                if covered == evidence_trace_ids
                else "some evidence traces are missing from replay input",
            }
        )

    passed_cases = sum(1 for case in cases if case["status"] == "pass")
    failed_cases = sum(1 for case in cases if case["status"] != "pass")
    return ReplayReport(
        replay_id=f"REPLAY-{patch.patch_id}",
        patch_id=patch.patch_id,
        status="pass" if cases and failed_cases == 0 else "fail",
        passed_cases=passed_cases,
        failed_cases=failed_cases,
        cases=cases,
        metadata={"engine": "assertion_simulation_v1"},
    )


def write_replay_report(root: Path, report: ReplayReport) -> Path:
    report_dir = root / LOCAL_DIR / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"{report.replay_id}.json"
    path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return path


def _patch_addresses_assertions(
    patch: PatchBundle,
    assertions: list[dict[str, Any]],
) -> bool:
    patch_layer = patch.metadata.get("patch_layer")
    diff = patch.diff.lower()
    for assertion in assertions:
        if assertion.get("type") == "forbidden_tool_call":
            tool = str(assertion.get("tool") or "").lower()
            if tool and tool in diff and patch_layer in {"tool_description", "permission_policy"}:
                return True
    return False
