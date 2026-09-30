"""Domain models for auditable, iterative harness search."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SearchSession:
    session_id: str
    issue_id: str
    baseline_state_id: str
    status: str
    created_at: str
    updated_at: str
    max_rounds: int
    candidates_per_round: int
    proposer_id: str
    evaluator_id: str
    search_case_ids: list[str] = field(default_factory=list)
    control_case_ids: list[str] = field(default_factory=list)
    holdout_case_ids: list[str] = field(default_factory=list)
    promoted_candidate_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SearchSession":
        return cls(
            session_id=str(data["session_id"]),
            issue_id=str(data["issue_id"]),
            baseline_state_id=str(data["baseline_state_id"]),
            status=str(data["status"]),
            created_at=str(data["created_at"]),
            updated_at=str(data["updated_at"]),
            max_rounds=int(data["max_rounds"]),
            candidates_per_round=int(data["candidates_per_round"]),
            proposer_id=str(data["proposer_id"]),
            evaluator_id=str(data["evaluator_id"]),
            search_case_ids=list(data.get("search_case_ids") or []),
            control_case_ids=list(data.get("control_case_ids") or []),
            holdout_case_ids=list(data.get("holdout_case_ids") or []),
            promoted_candidate_id=data.get("promoted_candidate_id"),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": "1", **self.__dict__}


@dataclass(frozen=True)
class ExperimentCase:
    case_id: str
    session_id: str
    trace_id: str
    split: str
    created_at: str
    payload: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExperimentCase":
        return cls(
            case_id=str(data["case_id"]),
            session_id=str(data["session_id"]),
            trace_id=str(data["trace_id"]),
            split=str(data["split"]),
            created_at=str(data["created_at"]),
            payload=dict(data.get("payload") or {}),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self, *, include_payload: bool = True) -> dict[str, Any]:
        value = {
            "schema_version": "1",
            "case_id": self.case_id,
            "session_id": self.session_id,
            "trace_id": self.trace_id,
            "split": self.split,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }
        if include_payload:
            value["payload"] = self.payload
        return value


@dataclass(frozen=True)
class CandidateHypothesis:
    statement: str
    expected_effect: str
    affected_case_classes: list[str]
    unaffected_case_classes: list[str]
    possible_confounds: list[str]
    disproof_condition: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CandidateHypothesis":
        return cls(
            statement=str(data["statement"]),
            expected_effect=str(data["expected_effect"]),
            affected_case_classes=list(data.get("affected_case_classes") or []),
            unaffected_case_classes=list(data.get("unaffected_case_classes") or []),
            possible_confounds=list(data.get("possible_confounds") or []),
            disproof_condition=str(data["disproof_condition"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class ExperimentCandidate:
    candidate_id: str
    session_id: str
    round_number: int
    parent_candidate_ids: list[str]
    hypothesis: CandidateHypothesis
    file_updates: list[dict[str, Any]]
    patch_bundle: dict[str, Any]
    status: str
    created_at: str
    proposer_id: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExperimentCandidate":
        return cls(
            candidate_id=str(data["candidate_id"]),
            session_id=str(data["session_id"]),
            round_number=int(data["round_number"]),
            parent_candidate_ids=list(data.get("parent_candidate_ids") or []),
            hypothesis=CandidateHypothesis.from_dict(dict(data["hypothesis"])),
            file_updates=list(data.get("file_updates") or []),
            patch_bundle=dict(data.get("patch_bundle") or {}),
            status=str(data["status"]),
            created_at=str(data["created_at"]),
            proposer_id=str(data["proposer_id"]),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "candidate_id": self.candidate_id,
            "session_id": self.session_id,
            "round_number": self.round_number,
            "parent_candidate_ids": self.parent_candidate_ids,
            "hypothesis": self.hypothesis.to_dict(),
            "file_updates": self.file_updates,
            "patch_bundle": self.patch_bundle,
            "status": self.status,
            "created_at": self.created_at,
            "proposer_id": self.proposer_id,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class ObjectiveVector:
    quality: float
    issue_resolution: float
    regression_free: float
    safety: float
    judge_confidence: float
    cost_usd: float
    latency_ms: float
    tool_calls: float
    human_interventions: float = 0.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ObjectiveVector":
        return cls(**{key: float(data.get(key) or 0.0) for key in cls.__annotations__})

    def to_dict(self) -> dict[str, float]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class CandidateEvaluation:
    evaluation_id: str
    session_id: str
    candidate_id: str
    split: str
    status: str
    created_at: str
    evaluator_id: str
    cases: list[dict[str, Any]]
    objectives: ObjectiveVector
    verification: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CandidateEvaluation":
        return cls(
            evaluation_id=str(data["evaluation_id"]),
            session_id=str(data["session_id"]),
            candidate_id=str(data["candidate_id"]),
            split=str(data["split"]),
            status=str(data["status"]),
            created_at=str(data["created_at"]),
            evaluator_id=str(data["evaluator_id"]),
            cases=list(data.get("cases") or []),
            objectives=ObjectiveVector.from_dict(dict(data.get("objectives") or {})),
            verification=dict(data.get("verification") or {}),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "evaluation_id": self.evaluation_id,
            "session_id": self.session_id,
            "candidate_id": self.candidate_id,
            "split": self.split,
            "status": self.status,
            "created_at": self.created_at,
            "evaluator_id": self.evaluator_id,
            "cases": self.cases,
            "objectives": self.objectives.to_dict(),
            "verification": self.verification,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class ParetoSnapshot:
    snapshot_id: str
    session_id: str
    round_number: int
    candidate_ids: list[str]
    dominated_candidate_ids: list[str]
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": "1", **self.__dict__}


@dataclass(frozen=True)
class SearchEvent:
    event_id: str
    session_id: str
    event_type: str
    created_at: str
    candidate_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": "1", **self.__dict__}
