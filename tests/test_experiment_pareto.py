from __future__ import annotations

from loopforge.experiments.models import CandidateEvaluation, ObjectiveVector
from loopforge.experiments.pareto import pareto_frontier


def evaluation(candidate_id: str, vector: ObjectiveVector, *, delta: float = 0.2) -> CandidateEvaluation:
    return CandidateEvaluation(
        evaluation_id=f"E-{candidate_id}",
        session_id="S-1",
        candidate_id=candidate_id,
        split="combined",
        status="pass",
        created_at="2026-01-01T00:00:00Z",
        evaluator_id="judge",
        cases=[],
        objectives=vector,
        verification={
            "verified": True,
            "holdout_isolated": True,
            "target_improvement_delta": delta,
        },
    )


def test_frontier_keeps_quality_cost_tradeoff_and_removes_dominated_candidate() -> None:
    quality = evaluation("quality", ObjectiveVector(0.95, 0.9, 1, 1, 0.9, 0.20, 500, 4))
    cheap = evaluation("cheap", ObjectiveVector(0.90, 0.85, 1, 1, 0.9, 0.05, 200, 2))
    dominated = evaluation("dominated", ObjectiveVector(0.80, 0.8, 1, 1, 0.8, 0.30, 700, 5))

    result = pareto_frontier([quality, cheap, dominated])

    assert result.candidate_ids == ["cheap", "quality"]
    assert result.dominated_candidate_ids == ["dominated"]


def test_frontier_rejects_unverified_or_non_improving_candidate() -> None:
    no_delta = evaluation("no-delta", ObjectiveVector(1, 1, 1, 1, 1, 0, 0, 0), delta=0)
    result = pareto_frontier([no_delta])
    assert result.candidate_ids == []
    assert result.ineligible_candidate_ids == ["no-delta"]
