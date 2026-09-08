"""Post-merge confirmation report model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ConfirmationReport:
    confirmation_id: str
    patch_id: str
    issue_id: str
    operation_ids: list[str]
    status: str
    outcome: str
    baseline_failure_rate: float
    observed_failure_rate: float
    observed_trace_count: int
    recurring_failure_count: int
    recommendation: str
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConfirmationReport":
        return cls(
            confirmation_id=str(data["confirmation_id"]),
            patch_id=str(data["patch_id"]),
            issue_id=str(data["issue_id"]),
            operation_ids=list(data.get("operation_ids") or []),
            status=str(data["status"]),
            outcome=str(data["outcome"]),
            baseline_failure_rate=float(data.get("baseline_failure_rate") or 0.0),
            observed_failure_rate=float(data.get("observed_failure_rate") or 0.0),
            observed_trace_count=int(data.get("observed_trace_count") or 0),
            recurring_failure_count=int(data.get("recurring_failure_count") or 0),
            recommendation=str(data["recommendation"]),
            created_at=str(data["created_at"]),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "confirmation_id": self.confirmation_id,
            "patch_id": self.patch_id,
            "issue_id": self.issue_id,
            "operation_ids": self.operation_ids,
            "status": self.status,
            "outcome": self.outcome,
            "baseline_failure_rate": self.baseline_failure_rate,
            "observed_failure_rate": self.observed_failure_rate,
            "observed_trace_count": self.observed_trace_count,
            "recurring_failure_count": self.recurring_failure_count,
            "recommendation": self.recommendation,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }
