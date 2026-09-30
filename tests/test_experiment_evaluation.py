from __future__ import annotations

from loopforge.experiments.evaluation import (
    PairwiseDecision,
    evaluate_candidate,
    qualify_pairwise_evaluator,
)
from loopforge.experiments.execution import ExecutionResult
from loopforge.experiments.models import ExperimentCase


class UnstableEvaluator:
    evaluator_id = "unstable-evaluator"

    def __init__(self) -> None:
        self.calls = 0

    def judge(self, case, baseline, candidate, context, *, candidate_first: bool):
        self.calls += 1
        score = 0.95 if self.calls % 2 else 0.2
        return PairwiseDecision(
            preferred="candidate" if self.calls % 2 else "baseline",
            candidate_quality=score,
            baseline_quality=0.5,
            candidate_issue_resolution=score,
            baseline_issue_resolution=0.5,
            candidate_safety=1.0,
            baseline_safety=1.0,
            confidence=0.9,
            abstain=False,
            rationale="intentionally unstable",
            violated_contracts=[],
            metadata={"candidate_first": candidate_first},
        )


def result(candidate_id: str, case_id: str) -> ExecutionResult:
    return ExecutionResult(
        candidate_id,
        case_id,
        "completed",
        {"answer": "x"},
        {"events": []},
        {"latency_ms": 1, "cost_usd": 0, "tool_calls": 0},
    )


def test_repeated_judge_disagreement_blocks_candidate() -> None:
    case = ExperimentCase(
        "CASE-1",
        "SEARCH-1",
        "TRACE-1",
        "search",
        "2026-01-01T00:00:00Z",
        {"inputs": {"query": "x"}},
    )
    evaluation = evaluate_candidate(
        "SEARCH-1",
        "CANDIDATE-1",
        [case],
        {case.case_id: result("BASELINE-1", case.case_id)},
        {case.case_id: result("CANDIDATE-1", case.case_id)},
        UnstableEvaluator(),
        {},
        repetitions=3,
    )

    assert evaluation.status == "fail"
    assert evaluation.verification["verified"] is False
    assert evaluation.verification["abstention_count"] == 1


def test_evaluator_identity_bias_fails_preflight() -> None:
    class BiasedEvaluator(UnstableEvaluator):
        evaluator_id = "biased"

        def judge(self, case, baseline, candidate, context, *, candidate_first: bool):
            return PairwiseDecision(
                "candidate", 0.9, 0.4, 0.9, 0.4, 1, 1, 0.9, False,
                "always favors candidate", [], {},
            )

    case = ExperimentCase(
        "CASE-1", "SEARCH-1", "TRACE-1", "search", "2026-01-01T00:00:00Z", {}
    )
    qualification = qualify_pairwise_evaluator(
        BiasedEvaluator(), case, result("BASELINE-1", case.case_id), {}
    )
    assert qualification["status"] == "fail"
    assert qualification["blocking_gate_eligible"] is False
