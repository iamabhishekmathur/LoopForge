from __future__ import annotations

import json
from pathlib import Path

from loopforge.improvements.planner import (
    build_improvement_plan,
    cluster_accepted_findings,
    collect_code_evidence,
)


class FixtureInvestigator:
    def investigate(self, packet: dict[str, object]) -> dict[str, object]:
        evidence = packet["code_evidence"]
        assert isinstance(evidence, list) and evidence
        item = evidence[0]
        assert isinstance(item, dict)
        evidence_id = item["evidence_id"]
        source_path = item["source_path"]
        return {
            "cluster_summary": "A caller supplies an undeclared template parameter.",
            "root_cause": {
                "hypothesis": "The caller and template parameter contracts diverged.",
                "confidence": 0.92,
                "evidence_ids": [evidence_id],
            },
            "ownership": [
                {
                    "source_path": source_path,
                    "symbol": "bind_template",
                    "evidence_ids": [evidence_id],
                }
            ],
            "alternatives": [
                {
                    "hypothesis": "The caller should omit the parameter.",
                    "how_to_disprove": "Inspect whether the template is intended to filter products.",
                }
            ],
            "recommended_change": {
                "summary": "Synchronize the caller and template parameter contracts.",
                "source_paths": [source_path],
                "symbols": ["bind_template"],
                "evidence_ids": [evidence_id],
            },
            "regression_evaluator": {
                "name": "template parameter contract",
                "positive_behavior": "Detect a caller passing an undeclared parameter.",
                "negative_behavior": "Accept calls whose parameters are fully declared.",
                "abstention_behavior": "Abstain when the selected template is unavailable.",
                "pass_criteria": "At least 0.9 detection and acceptance rates on labeled examples.",
            },
            "risks": ["Template semantics still require human review."],
            "patch_eligible": True,
        }


def _report(*, false_positive: bool = False) -> dict[str, object]:
    error = (
        'TemplateBindError("Unknown parameter: productrollup")\n\nTraceback:\n'
        '  File "/srv/app/pkg/templates.py", line 12, in bind_template'
    )
    records = []
    for trace_id, title in (("trace-1", "Template failed"), ("trace-2", "Binding error")):
        records.append(
            {
                "status": "complete",
                "trace_id": trace_id,
                "calibrated_decision": {
                    "findings": [
                        {
                            "finding_scope": "latent_system_failure",
                            "finding_type": "observed_error",
                            "title": title,
                            "actual_behavior": error,
                            "supporting_trace_evidence": [{"kind": "errors", "value": [error]}],
                        }
                    ]
                },
                "audit": {
                    "calibrated": {
                        "false_positive": false_positive,
                        "rationale": "fixture adjudication",
                    }
                },
            }
        )
    return {"records": records}


def test_repeated_errors_are_clustered_by_failure_anchor() -> None:
    clusters = cluster_accepted_findings(_report())

    assert len(clusters) == 1
    assert clusters[0]["occurrence_count"] == 2
    assert clusters[0]["trace_ids"] == ["trace-1", "trace-2"]


def test_code_evidence_follows_traceback_path_and_symbol(tmp_path: Path) -> None:
    source = tmp_path / "pkg" / "templates.py"
    source.parent.mkdir()
    source.write_text(
        "def bind_template(template, parameters):\n"
        "    allowed = template.parameters\n"
        "    return {key: value for key, value in parameters.items() if key in allowed}\n",
        encoding="utf-8",
    )
    cluster = cluster_accepted_findings(_report())[0]

    evidence = collect_code_evidence(tmp_path, cluster)

    assert evidence[0]["source_path"] == "pkg/templates.py"
    assert "traceback_path:srv/app/pkg/templates.py" in evidence[0]["match_reasons"]
    assert "bind_template" in evidence[0]["snippet"]


def test_improvement_plan_is_gated_and_does_not_modify_source(tmp_path: Path) -> None:
    source = tmp_path / "pkg" / "templates.py"
    source.parent.mkdir()
    original = "def bind_template(template, parameters):\n    return parameters\n"
    source.write_text(original, encoding="utf-8")
    report_path = tmp_path / "evaluation.json"
    report_path.write_text(json.dumps(_report()), encoding="utf-8")

    result = build_improvement_plan(tmp_path, report_path, FixtureInvestigator())
    payload = json.loads(result.report_path.read_text(encoding="utf-8"))

    assert result.cluster_count == 1
    assert result.reviewable_count == 1
    assert payload["mutated_customer_code"] is False
    assert payload["plans"][0]["patch_eligible"] is True
    assert source.read_text(encoding="utf-8") == original


def test_disputed_finding_cannot_be_patch_eligible(tmp_path: Path) -> None:
    source = tmp_path / "pkg" / "templates.py"
    source.parent.mkdir()
    source.write_text("def bind_template():\n    pass\n", encoding="utf-8")
    report_path = tmp_path / "evaluation.json"
    report_path.write_text(json.dumps(_report(false_positive=True)), encoding="utf-8")

    result = build_improvement_plan(tmp_path, report_path, FixtureInvestigator())
    payload = json.loads(result.report_path.read_text(encoding="utf-8"))

    assert result.reviewable_count == 0
    assert payload["plans"][0]["patch_eligible"] is False
    assert payload["plans"][0]["status"] == "needs_human_review"
