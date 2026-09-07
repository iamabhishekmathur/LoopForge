"""Issue model for the local closed-loop spine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Issue:
    issue_id: str
    title: str
    primary_ontology_id: str
    ontology_version: str
    failure_layer: str
    trace_observability: str
    severity: str
    confidence: float
    evidence_trace_ids: list[str]
    recommended_patch_layers: list[str]
    status: str = "open"
    secondary_ontology_ids: list[str] = field(default_factory=list)
    root_cause_hypotheses: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Issue":
        return cls(
            issue_id=str(data["issue_id"]),
            title=str(data["title"]),
            primary_ontology_id=str(data["primary_ontology_id"]),
            ontology_version=str(data["ontology_version"]),
            failure_layer=str(data["failure_layer"]),
            trace_observability=str(data["trace_observability"]),
            severity=str(data["severity"]),
            confidence=float(data["confidence"]),
            evidence_trace_ids=list(data["evidence_trace_ids"]),
            recommended_patch_layers=list(data.get("recommended_patch_layers") or []),
            status=str(data.get("status") or "open"),
            secondary_ontology_ids=list(data.get("secondary_ontology_ids") or []),
            root_cause_hypotheses=list(data.get("root_cause_hypotheses") or []),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "issue_id": self.issue_id,
            "title": self.title,
            "primary_ontology_id": self.primary_ontology_id,
            "ontology_version": self.ontology_version,
            "failure_layer": self.failure_layer,
            "trace_observability": self.trace_observability,
            "severity": self.severity,
            "confidence": self.confidence,
            "evidence_trace_ids": self.evidence_trace_ids,
            "recommended_patch_layers": self.recommended_patch_layers,
            "status": self.status,
            "secondary_ontology_ids": self.secondary_ontology_ids,
            "root_cause_hypotheses": self.root_cause_hypotheses,
            "metadata": self.metadata,
        }
