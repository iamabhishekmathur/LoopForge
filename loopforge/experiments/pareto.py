"""Hard-constraint filtering and Pareto-frontier selection."""

from __future__ import annotations

from dataclasses import dataclass

from loopforge.experiments.models import CandidateEvaluation, ObjectiveVector


MAXIMIZE = ("quality", "issue_resolution", "regression_free", "safety", "judge_confidence")
MINIMIZE = ("cost_usd", "latency_ms", "tool_calls", "human_interventions")


@dataclass(frozen=True)
class FrontierResult:
    candidate_ids: list[str]
    dominated_candidate_ids: list[str]
    ineligible_candidate_ids: list[str]


def hard_constraint_eligible(evaluation: CandidateEvaluation) -> bool:
    vector = evaluation.objectives
    verification = evaluation.verification
    return (
        evaluation.status == "pass"
        and vector.safety >= 0.99
        and vector.regression_free >= 0.95
        and vector.judge_confidence >= 0.70
        and verification.get("verified") is True
        and verification.get("holdout_isolated") is True
        and float(verification.get("target_improvement_delta", 0.0)) >= 0.05
    )


def dominates(left: ObjectiveVector, right: ObjectiveVector) -> bool:
    no_worse = all(getattr(left, key) >= getattr(right, key) for key in MAXIMIZE)
    no_worse = no_worse and all(
        getattr(left, key) <= getattr(right, key) for key in MINIMIZE
    )
    strictly_better = any(getattr(left, key) > getattr(right, key) for key in MAXIMIZE)
    strictly_better = strictly_better or any(
        getattr(left, key) < getattr(right, key) for key in MINIMIZE
    )
    return no_worse and strictly_better


def pareto_frontier(evaluations: list[CandidateEvaluation]) -> FrontierResult:
    eligible = [evaluation for evaluation in evaluations if hard_constraint_eligible(evaluation)]
    ineligible = sorted(
        evaluation.candidate_id
        for evaluation in evaluations
        if not hard_constraint_eligible(evaluation)
    )
    frontier: list[str] = []
    dominated: list[str] = []
    for candidate in eligible:
        is_dominated = any(
            other.candidate_id != candidate.candidate_id
            and dominates(other.objectives, candidate.objectives)
            for other in eligible
        )
        if is_dominated:
            dominated.append(candidate.candidate_id)
        else:
            frontier.append(candidate.candidate_id)
    return FrontierResult(
        candidate_ids=sorted(frontier),
        dominated_candidate_ids=sorted(dominated),
        ineligible_candidate_ids=ineligible,
    )
