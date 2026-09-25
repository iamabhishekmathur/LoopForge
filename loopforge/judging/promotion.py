"""Promote strongly supported judge hypotheses into reviewable issues."""

from __future__ import annotations

import hashlib
from typing import Any

from loopforge.models.hypothesis import HypothesisFinding
from loopforge.models.issue import Issue


MODEL_JUDGES = {"openai_compatible", "json_file"}
MIN_PROMOTION_CONFIDENCE = 0.80
MIN_JUDGEABILITY = 0.60

ONTOLOGY_BY_FINDING = {
    "intent_mismatch": "INTENT_ALIGNMENT_ERROR",
    "possible_intent_mismatch": "INTENT_ALIGNMENT_ERROR",
    "tool_selection_mismatch": "TOOL_SELECTION_ERROR",
    "missing_clarification": "CLARIFICATION_ERROR",
    "final_answer_unfaithful": "FINAL_ANSWER_FAITHFULNESS_ERROR",
    "guardrail_gap": "GUARDRAIL_ENFORCEMENT_ERROR",
    "context_misuse": "CONTEXT_USE_ERROR",
    "skill_contract_gap": "SKILL_CONTRACT_ERROR",
    "data_pipeline_gap": "DATA_PIPELINE_ERROR",
    "degraded_model_output": "MODEL_OUTPUT_DEGRADATION",
    "orchestration_gap": "ORCHESTRATION_ERROR",
    "observed_error": "EXECUTION_RECOVERY_ERROR",
}

PATCH_LAYERS_BY_FINDING = {
    "intent_mismatch": ["routing_policy", "system_prompt", "skill", "eval"],
    "possible_intent_mismatch": ["routing_policy", "system_prompt", "skill", "eval"],
    "tool_selection_mismatch": ["routing_policy", "tool_description", "skill", "eval"],
    "missing_clarification": ["system_prompt", "routing_policy", "skill", "eval"],
    "final_answer_unfaithful": ["system_prompt", "context_policy", "eval"],
    "guardrail_gap": ["permission_policy", "runtime_enforcement", "eval"],
    "context_misuse": ["context_policy", "retrieval_policy", "eval"],
    "skill_contract_gap": ["skill", "system_prompt", "eval"],
    "data_pipeline_gap": ["data_pipeline", "runtime_enforcement", "eval"],
    "degraded_model_output": ["data_pipeline", "model_config", "runtime_enforcement", "eval"],
    "orchestration_gap": ["runtime_orchestration", "routing_policy", "system_prompt", "eval"],
    "observed_error": ["runtime_orchestration", "tool_definition", "eval"],
}


def promotable_finding(finding: HypothesisFinding) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    judge = str(finding.metadata.get("judge") or "local")
    if judge not in MODEL_JUDGES:
        reasons.append("finding is not model-backed")
    if finding.confidence < MIN_PROMOTION_CONFIDENCE:
        reasons.append(f"confidence is below {MIN_PROMOTION_CONFIDENCE:.2f}")
    if finding.judgeability_score < MIN_JUDGEABILITY:
        reasons.append(f"judgeability is below {MIN_JUDGEABILITY:.2f}")
    if finding.finding_type not in ONTOLOGY_BY_FINDING:
        reasons.append("finding type has no issue mapping")
    if finding.metadata.get("resolution_state") == "resolved_in_trace":
        reasons.append("finding was resolved in the observed trace")
    if not finding.supporting_trace_evidence:
        reasons.append("trace evidence is missing")
    elif finding.metadata.get("model_supplied_trace_evidence") is not True:
        reasons.append("trace evidence was not explicitly cited by the model")
    if not finding.supporting_codebase_evidence:
        reasons.append("codebase evidence is missing")
    elif finding.metadata.get("model_supplied_codebase_evidence") is not True:
        reasons.append("codebase evidence was not explicitly cited by the model")
    if not finding.metadata.get("expected_behavior"):
        reasons.append("expected behavior is missing")
    if not finding.metadata.get("actual_behavior"):
        reasons.append("actual behavior is missing")
    return not reasons, reasons


def promote_findings(findings: list[HypothesisFinding]) -> list[Issue]:
    issues: list[Issue] = []
    for finding in findings:
        eligible, reasons = promotable_finding(finding)
        if not eligible:
            continue
        issue_id = _issue_id(finding.finding_id)
        ontology = ONTOLOGY_BY_FINDING[finding.finding_type]
        artifacts = [_artifact_link(item) for item in finding.supporting_codebase_evidence]
        artifacts = [item for item in artifacts if item is not None]
        diagnosis = {
            "expected_behavior": finding.metadata.get("expected_behavior"),
            "observed_behavior": finding.metadata.get("actual_behavior"),
            "behavior_gaps": [
                {
                    "label": finding.finding_type,
                    "confidence": finding.confidence,
                    "expected": finding.metadata.get("expected_behavior"),
                    "observed": finding.metadata.get("actual_behavior"),
                    "evidence": finding.supporting_trace_evidence,
                }
            ],
            "violated_contracts": finding.metadata.get("violated_contracts") or [],
            "resolution_state": finding.metadata.get("resolution_state") or "unknown",
            "calibration": {
                "judge": finding.metadata.get("judge"),
                "false_positive_risks": finding.metadata.get("false_positive_risks") or [],
                "promotion_threshold": MIN_PROMOTION_CONFIDENCE,
            },
        }
        issues.append(
            Issue(
                issue_id=issue_id,
                title=finding.title,
                primary_ontology_id=ontology,
                ontology_version="1",
                failure_layer=_failure_layer(finding.finding_type),
                trace_observability="high" if finding.judgeability_score >= 0.75 else "medium",
                severity=finding.severity,
                confidence=finding.confidence,
                evidence_trace_ids=[finding.trace_id],
                recommended_patch_layers=PATCH_LAYERS_BY_FINDING[finding.finding_type],
                secondary_ontology_ids=[],
                root_cause_hypotheses=[
                    {
                        "label": finding.finding_type,
                        "confidence": finding.confidence,
                        "explanation": finding.hypothesis,
                        "evidence": finding.supporting_trace_evidence,
                    }
                ],
                metadata={
                    "source": "hypothesis_judge",
                    "source_finding_id": finding.finding_id,
                    "source_finding": finding.to_dict(),
                    "implicated_tools": [],
                    "implicated_artifacts": artifacts,
                    "diagnosis": diagnosis,
                    "promotion": {
                        "eligible": True,
                        "threshold": MIN_PROMOTION_CONFIDENCE,
                        "rejection_reasons": reasons,
                    },
                },
            )
        )
    return issues


def _issue_id(finding_id: str) -> str:
    digest = hashlib.sha256(finding_id.encode("utf-8")).hexdigest()[:10].upper()
    return f"ISSUE-{digest}"


def _failure_layer(finding_type: str) -> str:
    if finding_type in {
        "tool_selection_mismatch",
        "missing_clarification",
        "intent_mismatch",
        "possible_intent_mismatch",
    }:
        return "orchestration"
    if finding_type == "guardrail_gap":
        return "governance"
    if finding_type in {"context_misuse", "final_answer_unfaithful"}:
        return "context_and_response"
    if finding_type == "skill_contract_gap":
        return "skill"
    if finding_type == "data_pipeline_gap":
        return "data_pipeline"
    if finding_type == "degraded_model_output":
        return "model"
    return "runtime"


def _artifact_link(evidence: dict[str, Any]) -> dict[str, Any] | None:
    path = evidence.get("source_path")
    if not path:
        return None
    return {
        "artifact_id": evidence.get("artifact_id") or f"contract:{path}",
        "artifact_type": evidence.get("contract_type") or "harness_contract",
        "path": str(path),
        "confidence": float(evidence.get("confidence") or 0.0),
        "sha256": evidence.get("sha256") or "",
        "reason": evidence.get("summary") or "codebase evidence cited by the model judge",
    }
