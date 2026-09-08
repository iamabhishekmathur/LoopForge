"""Issue resolution plan model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ResolutionPlan:
    plan_id: str
    issue_id: str
    status: str
    generated_at: str
    observed_failure: str
    evidence_trace_ids: list[str]
    contradictions: list[dict[str, Any]]
    root_cause_rankings: list[dict[str, Any]]
    recommended_next_action: str
    candidate_actions: list[dict[str, Any]]
    gate_blockers: list[dict[str, Any]] = field(default_factory=list)
    evidence_needed: list[str] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResolutionPlan":
        return cls(
            plan_id=str(data["plan_id"]),
            issue_id=str(data["issue_id"]),
            status=str(data["status"]),
            generated_at=str(data["generated_at"]),
            observed_failure=str(data["observed_failure"]),
            evidence_trace_ids=list(data.get("evidence_trace_ids") or []),
            contradictions=list(data.get("contradictions") or []),
            root_cause_rankings=list(data.get("root_cause_rankings") or []),
            recommended_next_action=str(data["recommended_next_action"]),
            candidate_actions=list(data.get("candidate_actions") or []),
            gate_blockers=list(data.get("gate_blockers") or []),
            evidence_needed=list(data.get("evidence_needed") or []),
            artifacts=list(data.get("artifacts") or []),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "plan_id": self.plan_id,
            "issue_id": self.issue_id,
            "status": self.status,
            "generated_at": self.generated_at,
            "observed_failure": self.observed_failure,
            "evidence_trace_ids": self.evidence_trace_ids,
            "contradictions": self.contradictions,
            "root_cause_rankings": self.root_cause_rankings,
            "recommended_next_action": self.recommended_next_action,
            "candidate_actions": self.candidate_actions,
            "gate_blockers": self.gate_blockers,
            "evidence_needed": self.evidence_needed,
            "artifacts": self.artifacts,
            "metadata": self.metadata,
        }
