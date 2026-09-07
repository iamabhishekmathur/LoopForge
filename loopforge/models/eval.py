"""Eval and evaluator models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EvalExample:
    eval_id: str
    issue_id: str
    source_trace_ids: list[str]
    primary_ontology_id: str
    ontology_version: str
    input: dict[str, Any]
    assertions: list[dict[str, Any]]
    status: str = "drafted"
    expected_behavior: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvalExample":
        return cls(
            eval_id=str(data["eval_id"]),
            issue_id=str(data["issue_id"]),
            source_trace_ids=list(data["source_trace_ids"]),
            primary_ontology_id=str(data["primary_ontology_id"]),
            ontology_version=str(data["ontology_version"]),
            input=dict(data["input"]),
            assertions=list(data["assertions"]),
            status=str(data.get("status") or "drafted"),
            expected_behavior=dict(data.get("expected_behavior") or {}),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "eval_id": self.eval_id,
            "issue_id": self.issue_id,
            "source_trace_ids": self.source_trace_ids,
            "primary_ontology_id": self.primary_ontology_id,
            "ontology_version": self.ontology_version,
            "input": self.input,
            "expected_behavior": self.expected_behavior,
            "assertions": self.assertions,
            "status": self.status,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class EvaluatorDefinition:
    evaluator_id: str
    eval_id: str
    issue_id: str
    failure_mode_id: str
    ontology_version: str
    evaluator_type: str
    output_type: str
    assertions: list[dict[str, Any]]
    status: str = "drafted"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvaluatorDefinition":
        return cls(
            evaluator_id=str(data["evaluator_id"]),
            eval_id=str(data["eval_id"]),
            issue_id=str(data["issue_id"]),
            failure_mode_id=str(data["failure_mode_id"]),
            ontology_version=str(data["ontology_version"]),
            evaluator_type=str(data["evaluator_type"]),
            output_type=str(data["output_type"]),
            assertions=list(data["assertions"]),
            status=str(data.get("status") or "drafted"),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "evaluator_id": self.evaluator_id,
            "eval_id": self.eval_id,
            "issue_id": self.issue_id,
            "failure_mode_id": self.failure_mode_id,
            "ontology_version": self.ontology_version,
            "evaluator_type": self.evaluator_type,
            "output_type": self.output_type,
            "assertions": self.assertions,
            "status": self.status,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class EvaluatorValidationRecord:
    evaluator_id: str
    failure_mode_id: str
    ontology_version: str
    evaluator_type: str
    output_type: str
    validation_status: str
    blocking_gate_eligible: bool
    positive_examples: list[str] = field(default_factory=list)
    negative_examples: list[str] = field(default_factory=list)
    false_positive_examples: list[str] = field(default_factory=list)
    false_negative_examples: list[str] = field(default_factory=list)
    true_positive_rate: float | None = None
    true_negative_rate: float | None = None
    precision: float | None = None
    recall: float | None = None
    minimum_sample_size_met: bool = False
    evidence_sources: list[str] = field(default_factory=list)
    read_test_once: bool = True
    pass_k_reliability: float | None = None
    pass_at_k_capability: float | None = None
    reset_replay_failure_rate: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvaluatorValidationRecord":
        return cls(
            evaluator_id=str(data["evaluator_id"]),
            failure_mode_id=str(data["failure_mode_id"]),
            ontology_version=str(data["ontology_version"]),
            evaluator_type=str(data["evaluator_type"]),
            output_type=str(data["output_type"]),
            validation_status=str(data["validation_status"]),
            blocking_gate_eligible=bool(data["blocking_gate_eligible"]),
            positive_examples=list(data.get("positive_examples") or []),
            negative_examples=list(data.get("negative_examples") or []),
            false_positive_examples=list(data.get("false_positive_examples") or []),
            false_negative_examples=list(data.get("false_negative_examples") or []),
            true_positive_rate=data.get("true_positive_rate"),
            true_negative_rate=data.get("true_negative_rate"),
            precision=data.get("precision"),
            recall=data.get("recall"),
            minimum_sample_size_met=bool(data.get("minimum_sample_size_met")),
            evidence_sources=list(data.get("evidence_sources") or []),
            read_test_once=bool(data.get("read_test_once", True)),
            pass_k_reliability=data.get("pass_k_reliability"),
            pass_at_k_capability=data.get("pass_at_k_capability"),
            reset_replay_failure_rate=data.get("reset_replay_failure_rate"),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "evaluator_id": self.evaluator_id,
            "failure_mode_id": self.failure_mode_id,
            "ontology_version": self.ontology_version,
            "evaluator_type": self.evaluator_type,
            "output_type": self.output_type,
            "validation_status": self.validation_status,
            "ai_drafted": True,
            "evidence_sources": self.evidence_sources,
            "positive_examples": self.positive_examples,
            "negative_examples": self.negative_examples,
            "false_positive_examples": self.false_positive_examples,
            "false_negative_examples": self.false_negative_examples,
            "true_positive_rate": self.true_positive_rate,
            "true_negative_rate": self.true_negative_rate,
            "precision": self.precision,
            "recall": self.recall,
            "minimum_sample_size_met": self.minimum_sample_size_met,
            "read_test_once": self.read_test_once,
            "pass_k_reliability": self.pass_k_reliability,
            "pass_at_k_capability": self.pass_at_k_capability,
            "reset_replay_failure_rate": self.reset_replay_failure_rate,
            "blocking_gate_eligible": self.blocking_gate_eligible,
            "metadata": self.metadata,
        }
