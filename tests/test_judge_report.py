from __future__ import annotations

from loopforge.judging.report import judge_evaluation_html


def test_judge_html_prioritizes_query_response_issue_recommendation_and_timeline() -> None:
    report = {
        "generated_at": "2026-10-04T12:00:00+00:00",
        "probabilistic_provider": "fixture",
        "records": [
            {
                "status": "complete",
                "trace_id": "trace-<unsafe>",
                "span_count": 1,
                "user_intent": "fallback query",
                "final_response": "fallback response",
                "calibrated_trace_resolution": {
                    "current_turn_request": "Compare revenue by region",
                    "resolved_terminal_outcome": "Revenue was returned for one region only.",
                },
                "calibrated_decision": {
                    "findings": [
                        {
                            "title": "Incomplete regional comparison",
                            "hypothesis": "The request required every region.",
                            "recommended_next_action": "Preserve all requested groups in the query plan.",
                            "resolution_state": "unresolved",
                        }
                    ]
                },
                "audit": {
                    "reference_assessment": {
                        "classification": "clear_issue",
                        "core_issue": "The answer omitted requested regions.",
                        "why_it_matters": "The user cannot make the requested comparison.",
                        "recommended_action": "Require the planner to preserve requested grouping dimensions.",
                    }
                },
                "probabilistic_evaluation": {
                    "evaluators": [
                        {
                            "name": "Request fulfillment",
                            "label": "issue",
                            "confidence": 0.91,
                            "issue": "Requested regions were omitted.",
                            "evidence_ids": ["sql-step"],
                        }
                    ]
                },
                "decision_support": {
                    "support": "strong",
                    "evaluator_confidence": 0.91,
                    "judge_agreement": True,
                    "evidence_coverage": 1.0,
                    "decision_stability": 1.0,
                    "challenge_pass_rate": 1.0,
                    "requires_escalation": False,
                    "checks": [{"check": "probability_integrity", "passed": True}],
                    "semantics": "Autonomous support is not ground truth.",
                },
                "trace_timeline": [
                    {
                        "step_id": "sql-step",
                        "name": "generate_sql",
                        "step_type": "tool_call",
                        "started_at": "2026-10-04T12:00:00+00:00",
                        "ended_at": "2026-10-04T12:00:01+00:00",
                        "input_preview": "region comparison",
                        "output_preview": "SELECT one_region",
                        "error": None,
                    }
                ],
            }
        ],
    }

    html = judge_evaluation_html(report)

    assert "User query" in html
    assert "Final agent response" in html
    assert "Core issue" in html
    assert "Recommended change" in html
    assert "Trace timeline" in html
    assert "generate_sql" in html
    assert 'class="step issue"' in html
    assert "trace-&lt;unsafe&gt;" in html
    assert "trace-<unsafe>" not in html
