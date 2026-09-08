"""Refinement operation ledger models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RefinementOperation:
    operation_id: str
    operation_type: str
    component_type: str
    artifact_id: str
    artifact_path: str
    issue_id: str
    patch_id: str
    status: str
    source_trace_ids: list[str]
    source_eval_ids: list[str]
    confidence: float
    rationale: str
    diff_summary: str
    provenance: dict[str, Any]
    created_at: str
    scope: str = "workflow"
    expected_outcome: str = ""
    validation_plan: str = ""
    rollback_plan: str = ""
    preview_diff: str = ""
    reviewer_boundary: str = "team_review"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RefinementOperation":
        return cls(
            operation_id=str(data["operation_id"]),
            operation_type=str(data["operation_type"]),
            component_type=str(data["component_type"]),
            artifact_id=str(data["artifact_id"]),
            artifact_path=str(data["artifact_path"]),
            issue_id=str(data["issue_id"]),
            patch_id=str(data["patch_id"]),
            status=str(data["status"]),
            source_trace_ids=list(data.get("source_trace_ids") or []),
            source_eval_ids=list(data.get("source_eval_ids") or []),
            confidence=float(data.get("confidence") or 0.0),
            rationale=str(data.get("rationale") or ""),
            diff_summary=str(data.get("diff_summary") or ""),
            provenance=dict(data.get("provenance") or {}),
            created_at=str(data["created_at"]),
            scope=str(data.get("scope") or "workflow"),
            expected_outcome=str(data.get("expected_outcome") or ""),
            validation_plan=str(data.get("validation_plan") or ""),
            rollback_plan=str(data.get("rollback_plan") or ""),
            preview_diff=str(data.get("preview_diff") or ""),
            reviewer_boundary=str(data.get("reviewer_boundary") or "team_review"),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "operation_id": self.operation_id,
            "operation_type": self.operation_type,
            "component_type": self.component_type,
            "artifact_id": self.artifact_id,
            "artifact_path": self.artifact_path,
            "issue_id": self.issue_id,
            "patch_id": self.patch_id,
            "status": self.status,
            "source_trace_ids": self.source_trace_ids,
            "source_eval_ids": self.source_eval_ids,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "diff_summary": self.diff_summary,
            "provenance": self.provenance,
            "created_at": self.created_at,
            "scope": self.scope,
            "expected_outcome": self.expected_outcome,
            "validation_plan": self.validation_plan,
            "rollback_plan": self.rollback_plan,
            "preview_diff": self.preview_diff,
            "reviewer_boundary": self.reviewer_boundary,
            "metadata": self.metadata,
        }
