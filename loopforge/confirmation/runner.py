"""Classify post-merge effect for a gated patch."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

from loopforge.models.confirmation import ConfirmationReport
from loopforge.models.patch import PatchBundle
from loopforge.paths import LOCAL_DIR


def confirm_patch_outcome(
    patch: PatchBundle,
    issue: dict[str, object],
    operations: list[dict[str, object]],
    *,
    observed_trace_count: int | None = None,
    recurring_failure_count: int | None = None,
    min_observed_traces: int = 5,
) -> ConfirmationReport:
    baseline_rate = _baseline_failure_rate(issue)
    operation_ids = [str(operation["operation_id"]) for operation in operations]
    if observed_trace_count is None or recurring_failure_count is None:
        return _report(
            patch,
            issue,
            operation_ids,
            status="insufficient_data",
            outcome="insufficient_data",
            baseline_failure_rate=baseline_rate,
            observed_failure_rate=0.0,
            observed_trace_count=0,
            recurring_failure_count=0,
            recommendation="continue_monitoring",
            metadata={"reason": "no post-merge observation window supplied"},
        )

    observed_failure_rate = (
        recurring_failure_count / observed_trace_count if observed_trace_count else 0.0
    )
    if observed_trace_count < min_observed_traces:
        return _report(
            patch,
            issue,
            operation_ids,
            status="insufficient_data",
            outcome="insufficient_data",
            baseline_failure_rate=baseline_rate,
            observed_failure_rate=round(observed_failure_rate, 4),
            observed_trace_count=observed_trace_count,
            recurring_failure_count=recurring_failure_count,
            recommendation="continue_monitoring",
            metadata={"reason": "not enough comparable post-merge traces"},
        )

    if observed_failure_rate > baseline_rate * 1.25:
        outcome = "regressed"
        recommendation = "reopen_issue"
    elif observed_failure_rate <= baseline_rate * 0.30:
        outcome = "confirmed"
        recommendation = "mark_pattern_trusted"
    elif observed_failure_rate >= baseline_rate * 0.70:
        outcome = "no_effect"
        recommendation = "revisit_patch_layer"
    else:
        outcome = "insufficient_data"
        recommendation = "continue_monitoring"

    return _report(
        patch,
        issue,
        operation_ids,
        status="complete" if outcome != "insufficient_data" else "insufficient_data",
        outcome=outcome,
        baseline_failure_rate=baseline_rate,
        observed_failure_rate=round(observed_failure_rate, 4),
        observed_trace_count=observed_trace_count,
        recurring_failure_count=recurring_failure_count,
        recommendation=recommendation,
        metadata={"min_observed_traces": min_observed_traces},
    )


def write_confirmation_report(root: Path, report: ConfirmationReport) -> Path:
    report_dir = root / LOCAL_DIR / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"{report.confirmation_id}.json"
    path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return path


def _baseline_failure_rate(issue: dict[str, object]) -> float:
    evidence_count = len(issue.get("evidence_trace_ids", []) or [])
    metadata = issue.get("metadata")
    diagnosis = metadata.get("diagnosis") if isinstance(metadata, dict) else None
    trace_scores = diagnosis.get("trace_scores") if isinstance(diagnosis, dict) else None
    baseline_total = len(trace_scores) if isinstance(trace_scores, list) else evidence_count
    if baseline_total <= 0:
        return 0.0
    return round(evidence_count / baseline_total, 4)


def _report(
    patch: PatchBundle,
    issue: dict[str, object],
    operation_ids: list[str],
    *,
    status: str,
    outcome: str,
    baseline_failure_rate: float,
    observed_failure_rate: float,
    observed_trace_count: int,
    recurring_failure_count: int,
    recommendation: str,
    metadata: dict[str, object],
) -> ConfirmationReport:
    return ConfirmationReport(
        confirmation_id=f"CONFIRM-{patch.patch_id}",
        patch_id=patch.patch_id,
        issue_id=str(issue["issue_id"]),
        operation_ids=operation_ids,
        status=status,
        outcome=outcome,
        baseline_failure_rate=baseline_failure_rate,
        observed_failure_rate=observed_failure_rate,
        observed_trace_count=observed_trace_count,
        recurring_failure_count=recurring_failure_count,
        recommendation=recommendation,
        created_at=datetime.now(UTC).isoformat(),
        metadata=metadata,
    )
