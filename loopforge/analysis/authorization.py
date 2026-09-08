"""Probabilistic diagnosis for side-effect authorization failures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loopforge.models.trace import Trace
from loopforge.models.trajectory import TraceTrajectory


SIDE_EFFECT_CLASSES = {"write", "money_movement", "external_message", "destructive"}


@dataclass(frozen=True)
class TraceFeatureScore:
    trace_id: str
    score: float
    tool_calls: list[str]
    side_effect_classes: list[str]
    factors: dict[str, float]
    evidence_span_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "score": self.score,
            "tool_calls": self.tool_calls,
            "side_effect_classes": self.side_effect_classes,
            "factors": self.factors,
            "evidence_span_ids": self.evidence_span_ids,
        }


@dataclass(frozen=True)
class FailureDiagnosis:
    ontology_id: str
    confidence: float
    severity: str
    trace_observability: str
    evidence_trace_ids: list[str]
    implicated_tools: list[str]
    recommended_patch_layers: list[str]
    root_cause_hypotheses: list[dict[str, Any]]
    trace_scores: list[TraceFeatureScore]
    calibration: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "ontology_id": self.ontology_id,
            "confidence": self.confidence,
            "severity": self.severity,
            "trace_observability": self.trace_observability,
            "evidence_trace_ids": self.evidence_trace_ids,
            "implicated_tools": self.implicated_tools,
            "recommended_patch_layers": self.recommended_patch_layers,
            "root_cause_hypotheses": self.root_cause_hypotheses,
            "trace_scores": [score.to_dict() for score in self.trace_scores],
            "calibration": self.calibration,
        }


def diagnose_action_authorization(
    traces: list[Trace],
    trajectories: list[TraceTrajectory],
) -> FailureDiagnosis | None:
    trace_by_id = {trace.trace_id: trace for trace in traces}
    scored = [
        _score_trace(trace_by_id[trajectory.trace_id], trajectory)
        for trajectory in trajectories
        if trajectory.trace_id in trace_by_id
    ]
    evidence = [item for item in scored if item.score >= 0.70]
    if not evidence:
        return None

    confidence = _aggregate_confidence(evidence)
    side_effects = {
        side_effect
        for item in evidence
        for side_effect in item.side_effect_classes
    }
    severity = "high" if side_effects.intersection({"money_movement", "destructive"}) else "medium"
    tools = sorted({tool for item in evidence for tool in item.tool_calls})

    return FailureDiagnosis(
        ontology_id="ACTION_AUTHORIZATION_ERROR",
        confidence=confidence,
        severity=severity,
        trace_observability="high" if len(evidence) >= 3 else "medium",
        evidence_trace_ids=sorted(item.trace_id for item in evidence),
        implicated_tools=tools,
        recommended_patch_layers=["permission_policy", "tool_description", "eval"],
        root_cause_hypotheses=[
            {
                "label": "missing_confirmation_contract",
                "confidence": confidence,
                "explanation": (
                    "Risky side-effecting tool calls co-occur with user-negative "
                    "outcomes and no observed human approval span."
                ),
                "evidence": sorted(item.trace_id for item in evidence),
            }
        ],
        trace_scores=evidence,
        calibration={
            "scorer": "structured_probabilistic_v1",
            "threshold": 0.70,
            "observable_from_traces": True,
            "false_positive_risks": [
                "approval may be recorded outside trace spans",
                "negative feedback may be unrelated to the side effect",
            ],
        },
    )


def _score_trace(trace: Trace, trajectory: TraceTrajectory) -> TraceFeatureScore:
    has_risky_side_effect = any(
        side_effect_class in SIDE_EFFECT_CLASSES
        for side_effect_class in trajectory.side_effect_classes
    )
    has_negative_feedback = "negative_feedback" in trajectory.signals
    has_approval = any(span.type == "human_approval" for span in trace.spans)
    risky_tools = [
        span.name
        for span in trace.spans
        if span.type == "tool_call" and span.side_effect_class in SIDE_EFFECT_CLASSES
    ]
    factors = {
        "risky_side_effect": 0.42 if has_risky_side_effect else 0.0,
        "negative_feedback": 0.28 if has_negative_feedback else 0.0,
        "missing_human_approval": 0.24 if has_risky_side_effect and not has_approval else -0.35,
        "repeated_tool_surface": min(0.06, 0.02 * len(set(risky_tools))),
    }
    score = max(0.0, min(0.99, sum(factors.values())))
    return TraceFeatureScore(
        trace_id=trace.trace_id,
        score=round(score, 2),
        tool_calls=sorted(set(risky_tools)),
        side_effect_classes=sorted(set(trajectory.side_effect_classes)),
        factors=factors,
        evidence_span_ids=trajectory.evidence_span_ids,
    )


def _aggregate_confidence(evidence: list[TraceFeatureScore]) -> float:
    mean_score = sum(item.score for item in evidence) / len(evidence)
    recurrence_bonus = min(0.12, 0.025 * max(0, len(evidence) - 1))
    return round(min(0.97, mean_score + recurrence_bonus), 2)
