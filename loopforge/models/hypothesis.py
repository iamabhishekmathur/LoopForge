"""Hypothesis-first judge models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class JudgeTask:
    task_id: str
    task_type: str
    question: str
    required_evidence: list[str]
    available_evidence: list[str]
    missing_evidence: list[str]
    judgeable: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "question": self.question,
            "required_evidence": self.required_evidence,
            "available_evidence": self.available_evidence,
            "missing_evidence": self.missing_evidence,
            "judgeable": self.judgeable,
        }


@dataclass(frozen=True)
class JudgePlan:
    plan_id: str
    trace_id: str
    judgeability_score: float
    tasks: list[JudgeTask]
    behavior_map_id: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "plan_id": self.plan_id,
            "trace_id": self.trace_id,
            "judgeability_score": self.judgeability_score,
            "tasks": [task.to_dict() for task in self.tasks],
            "behavior_map_id": self.behavior_map_id,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class HypothesisFinding:
    finding_id: str
    trace_id: str
    finding_type: str
    title: str
    hypothesis: str
    severity: str
    confidence: float
    judgeability_score: float
    supporting_trace_evidence: list[dict[str, Any]]
    supporting_codebase_evidence: list[dict[str, Any]]
    missing_evidence: list[str]
    recommended_next_action: str
    status: str = "open"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HypothesisFinding":
        return cls(
            finding_id=str(data["finding_id"]),
            trace_id=str(data["trace_id"]),
            finding_type=str(data["finding_type"]),
            title=str(data["title"]),
            hypothesis=str(data["hypothesis"]),
            severity=str(data["severity"]),
            confidence=float(data["confidence"]),
            judgeability_score=float(data["judgeability_score"]),
            supporting_trace_evidence=list(data.get("supporting_trace_evidence") or []),
            supporting_codebase_evidence=list(data.get("supporting_codebase_evidence") or []),
            missing_evidence=list(data.get("missing_evidence") or []),
            recommended_next_action=str(data["recommended_next_action"]),
            status=str(data.get("status") or "open"),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "finding_id": self.finding_id,
            "trace_id": self.trace_id,
            "finding_type": self.finding_type,
            "title": self.title,
            "hypothesis": self.hypothesis,
            "severity": self.severity,
            "confidence": self.confidence,
            "judgeability_score": self.judgeability_score,
            "supporting_trace_evidence": self.supporting_trace_evidence,
            "supporting_codebase_evidence": self.supporting_codebase_evidence,
            "missing_evidence": self.missing_evidence,
            "recommended_next_action": self.recommended_next_action,
            "status": self.status,
            "metadata": self.metadata,
        }

