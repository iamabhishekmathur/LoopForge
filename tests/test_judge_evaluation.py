from __future__ import annotations

from loopforge.judging.evaluation import summarize_evaluation


def test_judge_evaluation_summary_compares_false_positives_and_misses() -> None:
    records = [
        {
            "status": "complete",
            "legacy_decision": {"findings": [{"title": "weak accusation"}]},
            "calibrated_decision": {"abstain": True, "reason": "acceptable"},
            "audit": {
                "reference_assessment": {"classification": "acceptable_behavior"},
                "legacy": {
                    "false_positive": True,
                    "missed_issue": False,
                    "evidence_quality": 0.2,
                    "codebase_grounding": 0.1,
                    "actionability": 0.3,
                },
                "calibrated": {
                    "false_positive": False,
                    "missed_issue": False,
                    "evidence_quality": 0.8,
                    "codebase_grounding": 0.7,
                    "actionability": 0.6,
                },
                "preferred_variant": "calibrated",
            },
        },
        {"status": "failed", "error": "timeout"},
    ]

    metrics = summarize_evaluation(records)

    assert metrics["completed"] == 1
    assert metrics["failed"] == 1
    assert metrics["reference_acceptable"] == 1
    assert metrics["legacy"]["false_positives"] == 1
    assert metrics["legacy"]["active_flagged_traces"] == 1
    assert metrics["legacy"]["unknown_resolution_findings"] == 1
    assert metrics["calibrated"]["false_positives"] == 0
    assert metrics["preferred_variant"]["calibrated"] == 1
