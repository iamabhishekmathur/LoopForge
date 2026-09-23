"""Efficiency report for evidence and judge loops."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from loopforge.db import Store
from loopforge.evidence.archive import list_evidence
from loopforge.evidence.reducer import list_receipts
from loopforge.paths import LOCAL_DIR


@dataclass(frozen=True)
class EfficiencyReport:
    report_id: str
    generated_at: str
    metrics: dict[str, Any]
    gates: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "report_id": self.report_id,
            "generated_at": self.generated_at,
            "metrics": self.metrics,
            "gates": self.gates,
        }


def build_efficiency_report(root: Path) -> EfficiencyReport:
    store = Store.for_project(root)
    try:
        traces = store.list_traces()
        findings = store.list_hypothesis_findings()
        monitor_runs = store.list_monitor_runs()
    finally:
        store.close()

    evidence = list_evidence(root)
    receipts = list_receipts(root)
    trace_bytes = sum(_json_bytes(trace) for trace in traces)
    finding_bytes = sum(_json_bytes(finding) for finding in findings)
    evidence_bytes = sum(record.byte_count for record in evidence)
    reduced_bytes = sum(receipt.reduced_bytes for receipt in receipts)
    verified_receipts = [receipt for receipt in receipts if receipt.verification_status == "verified"]
    skipped_receipts = [receipt for receipt in receipts if receipt.verification_status == "skipped"]
    failed_receipts = [receipt for receipt in receipts if receipt.verification_status == "failed"]
    compression_ratio = round(reduced_bytes / evidence_bytes, 4) if evidence_bytes else None
    metrics = {
        "trace_count": len(traces),
        "finding_count": len(findings),
        "monitor_run_count": len(monitor_runs),
        "trace_bytes": trace_bytes,
        "finding_bytes": finding_bytes,
        "evidence_record_count": len(evidence),
        "evidence_bytes": evidence_bytes,
        "receipt_count": len(receipts),
        "verified_receipt_count": len(verified_receipts),
        "skipped_receipt_count": len(skipped_receipts),
        "failed_receipt_count": len(failed_receipts),
        "reduced_bytes": reduced_bytes,
        "compression_ratio": compression_ratio,
        "estimated_trace_tokens": _tokens(trace_bytes),
        "estimated_reduced_tokens": _tokens(reduced_bytes),
        "estimated_token_savings": max(0, _tokens(evidence_bytes) - _tokens(reduced_bytes)),
    }
    gates = [
        _gate(
            "evidence_archive_present",
            "pass" if len(evidence) > 0 else "warn",
            "Evidence archive has records." if evidence else "Run `loopforge evidence archive`.",
        ),
        _gate(
            "receipt_verification",
            "pass" if receipts and not failed_receipts else "warn" if not receipts else "fail",
            "All receipts verified."
            if receipts and not failed_receipts and not skipped_receipts
            else f"All reducible receipts verified; {len(skipped_receipts)} tiny records skipped."
            if receipts and not failed_receipts
            else "No receipts yet." if not receipts else f"{len(failed_receipts)} receipts failed.",
        ),
        _gate(
            "cost_reduction",
            "pass" if compression_ratio is not None and compression_ratio < 1 else "warn",
            "Reduced receipts are smaller than archived evidence."
            if compression_ratio is not None and compression_ratio < 1
            else "No verified size reduction measured yet.",
        ),
    ]
    return EfficiencyReport(
        report_id=f"EFF-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}",
        generated_at=datetime.now(UTC).isoformat(),
        metrics=metrics,
        gates=gates,
    )


def write_efficiency_report(root: Path, report: EfficiencyReport) -> Path:
    path = root / LOCAL_DIR / "reports" / f"{report.report_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    latest = root / LOCAL_DIR / "reports" / "latest-efficiency-report.json"
    latest.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def efficiency_report_markdown(report: EfficiencyReport) -> str:
    metrics = report.metrics
    lines = [
        f"# {report.report_id}",
        "",
        f"Generated: `{report.generated_at}`",
        "",
        "## Metrics",
        "",
    ]
    for key in sorted(metrics):
        lines.append(f"- {key}: `{metrics[key]}`")
    lines.extend(["", "## Gates", ""])
    for gate in report.gates:
        lines.append(f"- `{gate['status']}` {gate['name']}: {gate['detail']}")
    return "\n".join(lines)


def _json_bytes(value: Any) -> int:
    return len(json.dumps(value, sort_keys=True).encode("utf-8"))


def _tokens(byte_count: int) -> int:
    return int(round(byte_count / 4))


def _gate(name: str, status: str, detail: str) -> dict[str, Any]:
    return {"name": name, "status": status, "detail": detail}
