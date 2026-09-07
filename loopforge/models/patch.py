"""Patch bundle and gate report models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PatchBundle:
    patch_id: str
    issue_id: str
    target_artifacts: list[dict[str, Any]]
    diff: str
    new_eval_ids: list[str]
    risk_assessment: str
    rollback_plan: str
    status: str = "drafted"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PatchBundle":
        return cls(
            patch_id=str(data["patch_id"]),
            issue_id=str(data["issue_id"]),
            target_artifacts=list(data["target_artifacts"]),
            diff=str(data["diff"]),
            new_eval_ids=list(data.get("new_eval_ids") or []),
            risk_assessment=str(data.get("risk_assessment") or ""),
            rollback_plan=str(data.get("rollback_plan") or ""),
            status=str(data.get("status") or "drafted"),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "patch_id": self.patch_id,
            "issue_id": self.issue_id,
            "target_artifacts": self.target_artifacts,
            "diff": self.diff,
            "new_eval_ids": self.new_eval_ids,
            "risk_assessment": self.risk_assessment,
            "rollback_plan": self.rollback_plan,
            "status": self.status,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class GateReport:
    gate_report_id: str
    patch_id: str
    status: str
    recommendation: str
    suites: list[dict[str, Any]]
    target_issue: dict[str, Any] = field(default_factory=dict)
    cost_delta_percent: float = 0.0
    latency_p95_delta_percent: float = 0.0
    trust: dict[str, Any] = field(default_factory=dict)
    regressions: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GateReport":
        return cls(
            gate_report_id=str(data["gate_report_id"]),
            patch_id=str(data["patch_id"]),
            status=str(data["status"]),
            recommendation=str(data["recommendation"]),
            suites=list(data["suites"]),
            target_issue=dict(data.get("target_issue") or {}),
            cost_delta_percent=float(data.get("cost_delta_percent") or 0.0),
            latency_p95_delta_percent=float(data.get("latency_p95_delta_percent") or 0.0),
            trust=dict(data.get("trust") or {}),
            regressions=list(data.get("regressions") or []),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "gate_report_id": self.gate_report_id,
            "patch_id": self.patch_id,
            "status": self.status,
            "recommendation": self.recommendation,
            "target_issue": self.target_issue,
            "suites": self.suites,
            "cost_delta_percent": self.cost_delta_percent,
            "latency_p95_delta_percent": self.latency_p95_delta_percent,
            "trust": self.trust,
            "regressions": self.regressions,
            "metadata": self.metadata,
        }
