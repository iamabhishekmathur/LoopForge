"""Probabilistic refiner-pass scoring interfaces."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from loopforge.models.issue import Issue


@dataclass(frozen=True)
class RefinerPassCandidate:
    pass_name: str
    component_type: str
    layer: str
    risk: str
    score: float
    rationale: str
    evidence: dict[str, object] = field(default_factory=dict)


class RefinerModel(Protocol):
    def score_passes(
        self,
        issue: Issue,
        passes: list[dict[str, str]],
        preferred_layer: str | None = None,
    ) -> list[RefinerPassCandidate]:
        """Return ranked refiner-pass candidates for an issue."""


class LocalProbabilisticRefinerModel:
    """Feature-based local fallback for pass ranking.

    This is intentionally simple but probabilistic in shape: each candidate gets
    a calibrated confidence-like score derived from issue confidence, trace
    evidence, implicated artifact confidence, recommended layers, and risk.
    """

    def score_passes(
        self,
        issue: Issue,
        passes: list[dict[str, str]],
        preferred_layer: str | None = None,
    ) -> list[RefinerPassCandidate]:
        candidates = [
            self._score_pass(issue, refiner_pass, preferred_layer)
            for refiner_pass in passes
        ]
        return sorted(candidates, key=lambda candidate: candidate.score, reverse=True)

    def _score_pass(
        self,
        issue: Issue,
        refiner_pass: dict[str, str],
        preferred_layer: str | None,
    ) -> RefinerPassCandidate:
        layer = refiner_pass["layer"]
        artifact_confidence = _artifact_confidence(issue, layer)
        evidence_score = min(len(issue.evidence_trace_ids) / 5, 1.0)
        recommended_bonus = 0.12 if layer in issue.recommended_patch_layers else 0.0
        preferred_bonus = 0.30 if preferred_layer == layer else 0.0
        risk_penalty = {"low": 0.0, "medium": 0.05, "high": 0.12}.get(
            refiner_pass["risk"],
            0.08,
        )
        raw = (
            issue.confidence * 0.45
            + artifact_confidence * 0.25
            + evidence_score * 0.18
            + recommended_bonus
            + preferred_bonus
            - risk_penalty
        )
        score = round(max(0.0, min(raw, 0.99)), 4)
        rationale = (
            f"score={score} from issue_confidence={issue.confidence:.2f}, "
            f"artifact_confidence={artifact_confidence:.2f}, "
            f"evidence_traces={len(issue.evidence_trace_ids)}, risk={refiner_pass['risk']}"
        )
        return RefinerPassCandidate(
            pass_name=refiner_pass["name"],
            component_type=refiner_pass["component_type"],
            layer=layer,
            risk=refiner_pass["risk"],
            score=score,
            rationale=rationale,
            evidence={
                "issue_confidence": issue.confidence,
                "artifact_confidence": artifact_confidence,
                "evidence_trace_count": len(issue.evidence_trace_ids),
                "recommended_layer": layer in issue.recommended_patch_layers,
                "preferred_layer": preferred_layer == layer,
            },
        )


def _artifact_confidence(issue: Issue, layer: str) -> float:
    expected_types = {
        "tool_description": {"tool_definition"},
        "permission_policy": {"permission_policy"},
        "system_prompt": {"system_prompt"},
        "skill": {"skill"},
        "routing_policy": {"routing_policy"},
        "context_policy": {"context_policy"},
        "retrieval_policy": {"context_policy", "retrieval_policy"},
        "evaluator": {"eval_suite", "eval_dataset"},
        "subagent_spec": {"sub_agent", "agent_graph"},
    }.get(layer, set())
    artifacts = issue.metadata.get("implicated_artifacts", [])
    if not isinstance(artifacts, list):
        return 0.0
    confidences = [
        float(artifact.get("confidence") or 0.0)
        for artifact in artifacts
        if isinstance(artifact, dict)
        and (not expected_types or artifact.get("artifact_type") in expected_types)
    ]
    return max(confidences) if confidences else 0.0
