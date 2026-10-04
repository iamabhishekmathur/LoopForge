from __future__ import annotations

from loopforge.judging.probabilistic import (
    EVALUATOR_SPECS,
    OpenAICompatibleProbabilisticEvaluator,
    autonomous_decision_support,
    build_evidence_ablation_challenge,
    normalize_evaluator_result,
)


def test_probabilistic_evaluator_normalizes_every_dimension_and_entropy() -> None:
    result = normalize_evaluator_result(
        {
            "evaluators": [
                {
                    "evaluator_id": "request_fulfillment",
                    "label": "issue",
                    "probabilities": {
                        "pass": 1,
                        "issue": 7,
                        "uncertain": 2,
                        "not_applicable": 0,
                    },
                    "evidence_ids": ["step-2"],
                    "issue": "The answer omitted the requested comparison.",
                }
            ]
        },
        provider="fixture",
    )

    assert len(result["evaluators"]) == len(EVALUATOR_SPECS)
    request = result["evaluators"][0]
    assert request["label"] == "issue"
    assert request["probabilities"]["issue"] == 0.7
    assert 0 < request["entropy"] < 1
    assert sum(request["probabilities"].values()) == 1.0
    assert result["evaluators"][1]["label"] == "uncertain"


def test_openai_proxy_sends_bounded_dimensions_and_returns_decisions() -> None:
    captured = {}

    def request_json(system_prompt: str, user_payload: str):
        captured["system"] = system_prompt
        captured["payload"] = user_payload
        return {
            "evaluators": [
                {
                    "evaluator_id": spec.evaluator_id,
                    "label": "pass",
                    "probabilities": {
                        "pass": 0.9,
                        "issue": 0.03,
                        "uncertain": 0.05,
                        "not_applicable": 0.02,
                    },
                    "rationale": "The visible evidence supports the behavior.",
                }
                for spec in EVALUATOR_SPECS
            ]
        }

    evaluator = OpenAICompatibleProbabilisticEvaluator(request_json=request_json)
    result = evaluator.evaluate({"model_resolved_trace": {"current_turn_request": "Help"}})

    assert "bounded evaluator" in captured["system"]
    assert "request_fulfillment" in captured["payload"]
    assert result["summary"]["issue_count"] == 0
    assert result["summary"]["mean_confidence"] == 0.9


def test_autonomous_support_is_strong_when_independent_signals_agree() -> None:
    evaluation = normalize_evaluator_result(
        {
            "evaluators": [
                {
                    "evaluator_id": spec.evaluator_id,
                    "label": "issue" if spec.evaluator_id == "request_fulfillment" else "pass",
                    "probabilities": (
                        {"pass": 0.02, "issue": 0.94, "uncertain": 0.03, "not_applicable": 0.01}
                        if spec.evaluator_id == "request_fulfillment"
                        else {"pass": 0.94, "issue": 0.02, "uncertain": 0.03, "not_applicable": 0.01}
                    ),
                    "evidence_ids": ["step-2"],
                }
                for spec in EVALUATOR_SPECS
            ]
        },
        provider="fixture",
    )
    decision = {
        "findings": [
            {
                "finding_type": "intent_mismatch",
                "supporting_trace_evidence": [{"kind": "step", "value": "step-2"}],
            }
        ]
    }

    support = autonomous_decision_support(
        evaluation,
        audit={"reference_assessment": {"classification": "clear_issue"}},
        final_decision=decision,
        draft_decision=decision,
    )

    assert support["support"] == "strong"
    assert support["judge_agreement"] is True
    assert support["evidence_coverage"] == 1.0
    assert support["decision_stability"] == 1.0
    assert support["requires_escalation"] is False


def test_autonomous_support_escalates_disagreement_without_claiming_ground_truth() -> None:
    evaluation = normalize_evaluator_result(
        {
            "evaluators": [
                {
                    "evaluator_id": "request_fulfillment",
                    "label": "pass",
                    "probabilities": {
                        "pass": 0.9,
                        "issue": 0.03,
                        "uncertain": 0.05,
                        "not_applicable": 0.02,
                    },
                }
            ]
        },
        provider="fixture",
    )

    support = autonomous_decision_support(
        evaluation,
        audit={"reference_assessment": {"classification": "likely_issue"}},
        final_decision={"abstain": True, "findings": []},
        draft_decision={"abstain": True, "findings": []},
    )

    assert support["support"] in {"weak", "moderate"}
    assert support["judge_agreement"] is False
    assert support["requires_escalation"] is True
    assert "not ground truth" in support["semantics"]


def test_evidence_ablation_challenge_removes_outcome_tools_and_contracts() -> None:
    original = {
        "model_resolved_trace": {
            "current_turn_request": "Find revenue",
            "resolved_terminal_outcome": "Revenue is 10",
            "outcome_kind": "user_facing_answer",
            "outcome_complete": True,
            "supporting_evidence": [{"reference": "step-2"}],
        },
        "observed_run": {
            "final_response": "Revenue is 10",
            "steps": [{"step_id": "step-2"}],
            "tool_calls": ["query"],
            "metadata": {"tool_actions": [{"name": "query"}]},
        },
        "behavior_map": {
            "contracts": [{"contract_id": "C1"}],
            "tool_catalog": [{"name": "query"}],
        },
    }

    challenge = build_evidence_ablation_challenge(original)

    assert challenge["model_resolved_trace"]["current_turn_request"] == "Find revenue"
    assert challenge["model_resolved_trace"]["resolved_terminal_outcome"] is None
    assert challenge["observed_run"]["steps"] == []
    assert challenge["observed_run"]["metadata"]["tool_actions"] == []
    assert challenge["behavior_map"]["contracts"] == []
    assert original["model_resolved_trace"]["resolved_terminal_outcome"] == "Revenue is 10"
