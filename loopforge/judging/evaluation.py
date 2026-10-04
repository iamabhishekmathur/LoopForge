"""Evaluate probabilistic judge quality on real traces without mutating issue state."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from loopforge.db import Store
from loopforge.judging.behavior_map import build_behavior_map
from loopforge.judging.hypothesis import judge_hypotheses
from loopforge.judging.interpreter import interpret_trace
from loopforge.judging.model_judge import (
    JudgeDecision,
    OpenAICompatibleHypothesisJudge,
    build_hypothesis_judge_payload,
    build_judge_review_packet,
)
from loopforge.judging.probabilistic import (
    JevProbabilisticEvaluator,
    OpenAICompatibleProbabilisticEvaluator,
    ProbabilisticEvaluator,
    autonomous_decision_support,
    build_evidence_ablation_challenge,
)
from loopforge.judging.report import write_judge_evaluation_html
from loopforge.judging.planner import plan_judges
from loopforge.models.harness import HarnessArtifact
from loopforge.models.trace import Trace
from loopforge.paths import LOCAL_DIR
from loopforge.privacy.redaction import sanitize_for_external_llm
from loopforge.traces.quality import is_analysis_eligible_trace
from loopforge.traces.selection import select_judge_cases


JUDGE_EVALUATOR_PROMPT = """You evaluate another LLM judge that reviews AI-agent traces without ground truth.

First independently assess the trace using only the supplied sanitized evidence packet. Assess both the quality of the agent response and latent system failures revealed by tool results, diagnostics, generated queries, or terminal structured actions. A diagnostic agent can behave correctly while proving that another harness component failed; classify that trace as an issue when the latent failure is sufficiently supported. Decide whether there is a clear issue, a likely issue, acceptable behavior, or insufficient evidence. Then assess the legacy and calibrated judge decisions. A useful issue must identify a behavior gap that is supported by trace evidence and codebase-derived contract evidence. Expected clarification, expected control flow, UI handoffs, and extraction ambiguity are not failures.

An intentional fallback can still prove a latent upstream failure when a component expected to train or operate normally instead emits materially degraded or uncalibrated output. Do not classify that condition as acceptable merely because fallback control flow executed as designed or the outer agent disclosed it. Judge the degraded component separately from the diagnostic agent.

Do not expand the user's request when assessing answer completeness. For ranked, filtered, or scored results, the eligible or scoreable population is the operational denominator. A response stating "X of Y" explicitly supplies Y; do not require a raw or ineligible population unless the user or a supplied contract explicitly asks for it.

Use calibrated_trace_resolution.answer_requirements as the pre-answer intent contract. An agent-response finding must cite and actually violate a requirement marked required; optional context is not a behavior gap. Latent-system failures remain independent of answer requirements.

Respect fulfillment_timing. A clarification or expected human-input pause does not violate an after_interaction_or_execution deliverable merely because the eventual result is not present in that turn. A missing_clarification issue requires a before_side_effect prerequisite that was actually skipped. If the user already answered yes to a confirmation question, do not require another confirmation. A bare analysis or mission name normally requests execution, not an immediate explanation of the name.

Score evidence quality, codebase grounding, and actionability from 0 to 1. Mark a false positive when a decision flags acceptable behavior or relies on unsupported assumptions. A purported finding whose hypothesis says the agent behaved correctly or that no behavior gap exists is always a false positive, regardless of confidence. Treat the calibrated trace resolution's terminal structured action as later and more authoritative than an intermediate final_response extraction. Do not call an answer incomplete when the terminal Diagnosis or answer action contains the requested result. Mark a missed issue when your independent assessment identifies a likely or clear issue absent from the decision. Do not reward verbosity. Return JSON only.

The audit labels describe different failure modes. If a decision has no findings, false_positive must be false; an incorrect abstention is a missed_issue, not a false_positive.

Also return a concise human summary. core_issue must name the single most important gap in plain language, why_it_matters must state the concrete impact, and recommended_action must name the smallest useful harness change. Each field must be one short sentence. For acceptable behavior, core_issue must say that no material issue was found and recommended_action must say that no harness change is recommended.
"""


AUDIT_CONTRACT = {
    "reference_assessment": {
        "classification": "clear_issue|likely_issue|acceptable_behavior|insufficient_evidence",
        "issue_types": ["string"],
        "rationale": "string",
        "expected_behavior": "string or null",
        "actual_behavior": "string or null",
        "core_issue": "one short sentence",
        "why_it_matters": "one short sentence",
        "recommended_action": "one short sentence",
    },
    "legacy": {
        "false_positive": "boolean",
        "missed_issue": "boolean",
        "evidence_quality": "0..1",
        "codebase_grounding": "0..1",
        "actionability": "0..1",
        "rationale": "string",
    },
    "calibrated": {
        "false_positive": "boolean",
        "missed_issue": "boolean",
        "evidence_quality": "0..1",
        "codebase_grounding": "0..1",
        "actionability": "0..1",
        "rationale": "string",
    },
    "preferred_variant": "legacy|calibrated|tie|neither",
}


@dataclass(frozen=True)
class JudgeEvaluationResult:
    input_trace_count: int
    trace_count: int
    auxiliary_trace_count: int
    excluded_trace_count: int
    completed_count: int
    failed_count: int
    report_path: Path
    html_report_path: Path
    metrics: dict[str, Any]


def evaluate_judge_variants(
    root: Path,
    *,
    endpoint: str,
    model: str,
    api_key_env: str = "OPENAI_API_KEY",
    review_model: str | None = None,
    limit: int | None = None,
    trace_ids: list[str] | None = None,
    timeout_seconds: float = 90.0,
    workers: int = 1,
    probabilistic_provider: str = "openai",
    probabilistic_model: str | None = None,
    probabilistic_endpoint: str | None = None,
    probabilistic_api_key_env: str | None = None,
) -> JudgeEvaluationResult:
    """Compare legacy and calibrated judges against an independent model audit."""

    store = Store.for_project(root)
    try:
        payloads = [payload for payload in store.list_traces() if is_analysis_eligible_trace(payload)]
        if trace_ids:
            selected_ids = set(trace_ids)
            payloads = [payload for payload in payloads if payload["trace_id"] in selected_ids]
        selection = select_judge_cases([Trace.from_dict(payload) for payload in payloads])
        traces = selection.cases[:limit] if limit is not None else selection.cases
        artifacts = [HarnessArtifact.from_dict(item) for item in store.list_harness_artifacts()]
    finally:
        store.close()

    behavior_map = build_behavior_map(artifacts)
    legacy_judge = OpenAICompatibleHypothesisJudge(
        endpoint=endpoint,
        model=model,
        api_key_env=api_key_env,
        timeout_seconds=timeout_seconds,
        max_payload_chars=90000,
        payload_variant="legacy",
        critic_enabled=False,
    )
    calibrated_judge = OpenAICompatibleHypothesisJudge(
        endpoint=endpoint,
        model=model,
        api_key_env=api_key_env,
        timeout_seconds=timeout_seconds,
        max_payload_chars=90000,
        payload_variant="calibrated",
        critic_enabled=True,
        review_model=review_model,
    )
    bounded_evaluator: ProbabilisticEvaluator
    if probabilistic_provider == "jev":
        bounded_evaluator = JevProbabilisticEvaluator(
            endpoint=probabilistic_endpoint or "https://jevmodel.org/v1/systemone",
            model=probabilistic_model or "jev-latest",
            api_key_env=probabilistic_api_key_env or "JEVMODEL_API_KEY",
            timeout_seconds=timeout_seconds,
        )
    elif probabilistic_provider == "openai":
        classifier_model = probabilistic_model or model

        def request_probabilistic_json(system_prompt: str, user_payload: str) -> dict[str, Any]:
            return calibrated_judge._request_json(
                system_prompt,
                user_payload,
                model=classifier_model,
                operation="probabilistic_evaluator",
            )

        bounded_evaluator = OpenAICompatibleProbabilisticEvaluator(
            request_json=request_probabilistic_json
        )
    else:
        raise ValueError(f"unsupported probabilistic evaluator provider: {probabilistic_provider}")

    def evaluate_trace(trace: Trace) -> dict[str, Any]:
        observed = interpret_trace(trace)
        plan = plan_judges(observed, behavior_map)
        local_findings = judge_hypotheses(observed, plan, behavior_map)
        record: dict[str, Any] = {
            "trace_id": trace.trace_id,
            "span_count": len(trace.spans),
            "judgeability_score": observed.judgeability_score,
            "status": "complete",
        }
        try:
            variant_errors: dict[str, str] = {}
            try:
                legacy = legacy_judge.decide(observed, plan, behavior_map, local_findings)
            except Exception as exc:
                variant_errors["legacy"] = str(exc)
                legacy = _failed_variant_decision("legacy", exc)
            calibrated = calibrated_judge.decide(observed, plan, behavior_map, local_findings)
            evidence_packet = build_hypothesis_judge_payload(
                observed,
                plan,
                behavior_map,
                local_findings,
                variant="calibrated",
            )
            sanitized = sanitize_for_external_llm(evidence_packet)
            compact_packet = build_judge_review_packet(
                sanitized.value,
                interpretation=calibrated.interpretation,
            )
            probabilistic_evaluation = bounded_evaluator.evaluate(compact_packet)
            evidence_ablation = bounded_evaluator.evaluate(
                build_evidence_ablation_challenge(compact_packet)
            )
            challenge_results = [
                {
                    "challenge_id": "evidence_ablation_requires_uncertainty",
                    "result": evidence_ablation,
                }
            ]
            audit_request = {
                "task": "Independently assess this trace, then compare both judge variants.",
                "output_contract": AUDIT_CONTRACT,
                "evidence_packet": compact_packet,
                "legacy_decision": legacy.payload,
                "calibrated_decision": calibrated.payload,
                "calibrated_trace_resolution": calibrated.interpretation,
                "variant_errors": variant_errors,
            }
            audit = calibrated_judge._request_json(
                JUDGE_EVALUATOR_PROMPT,
                calibrated_judge._serialize_payload(audit_request),
                model=review_model,
                operation="judge_adjudicator",
            )
            audit = _normalize_audit_payload(
                audit,
                decisions={
                    "legacy": legacy.payload,
                    "calibrated": calibrated.payload,
                },
            )
            draft_merged = (
                (calibrated.draft_payload or {}).get("merged")
                if isinstance(calibrated.draft_payload, dict)
                else None
            )
            decision_support = autonomous_decision_support(
                probabilistic_evaluation,
                audit=audit,
                final_decision=calibrated.payload,
                draft_decision=draft_merged,
                challenge_results=challenge_results,
            )
            record.update(
                {
                    "user_intent": observed.user_intent,
                    "final_response": observed.final_response,
                    "legacy_decision": legacy.payload,
                    "calibrated_decision": calibrated.payload,
                    "calibrated_trace_resolution": calibrated.interpretation,
                    "calibrated_investigator_draft": calibrated.draft_payload,
                    "probabilistic_evaluation": probabilistic_evaluation,
                    "decision_support": decision_support,
                    "autonomous_challenges": challenge_results,
                    "audit": audit,
                    "trace_timeline": [
                        {
                            "step_id": span.span_id,
                            "name": span.name,
                            "step_type": span.type,
                            "started_at": span.started_at,
                            "ended_at": span.ended_at,
                            "input_preview": observed.steps[index].input_preview,
                            "output_preview": observed.steps[index].output_preview,
                            "error": observed.steps[index].error,
                        }
                        for index, span in enumerate(trace.spans)
                    ],
                    "variant_errors": variant_errors,
                    "sanitization": {
                        "evidence_replacements": sanitized.replacement_count,
                        "evidence_replacement_types": sanitized.replacement_types,
                        "legacy_replacements": legacy.sanitized_replacement_count,
                        "calibrated_replacements": calibrated.sanitized_replacement_count,
                    },
                }
            )
        except Exception as exc:
            record["status"] = "failed"
            record["error"] = str(exc)
        return record

    worker_count = max(1, min(8, workers))
    if worker_count == 1:
        records = [evaluate_trace(trace) for trace in traces]
    else:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            records = list(executor.map(evaluate_trace, traces))

    metrics = summarize_evaluation(records)
    generated_at = datetime.now(timezone.utc).isoformat()
    report = {
        "schema_version": "2",
        "generated_at": generated_at,
        "evaluation_type": "hypothesis_judge_comparison",
        "model": model,
        "review_model": review_model or model,
        "probabilistic_provider": bounded_evaluator.provider_id,
        "probabilistic_model": (
            probabilistic_model
            or ("jev-latest" if probabilistic_provider == "jev" else model)
        ),
        "workers": worker_count,
        "input_trace_count": len(payloads),
        "trace_count": len(traces),
        "trace_selection": {
            "canonical_case_count": len(selection.cases),
            "auxiliary_trace_count": len(selection.auxiliary_trace_ids),
            "excluded_trace_count": len(selection.excluded_trace_ids),
            "auxiliary_trace_ids": selection.auxiliary_trace_ids,
            "excluded_trace_ids": selection.excluded_trace_ids,
        },
        "metrics": metrics,
        "records": records,
        "limitations": [
            "The reference assessment is probabilistic model adjudication, not ground truth.",
            "Evaluator probabilities are decision uncertainty, not observed correctness rates.",
            "LoopForge validates decisions autonomously through independent agreement, evidence coverage, stability, and challenge checks.",
        ],
    }
    report_dir = root / LOCAL_DIR / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = report_dir / f"judge-evaluation-{stamp}.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    latest_path = report_dir / "latest-judge-evaluation.json"
    latest_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    html_report_path = write_judge_evaluation_html(report, report_path)
    write_judge_evaluation_html(report, latest_path)
    return JudgeEvaluationResult(
        input_trace_count=len(payloads),
        trace_count=len(traces),
        auxiliary_trace_count=len(selection.auxiliary_trace_ids),
        excluded_trace_count=len(selection.excluded_trace_ids),
        completed_count=sum(record["status"] == "complete" for record in records),
        failed_count=sum(record["status"] == "failed" for record in records),
        report_path=report_path,
        html_report_path=html_report_path,
        metrics=metrics,
    )


def _failed_variant_decision(variant: str, error: Exception) -> JudgeDecision:
    return JudgeDecision(
        payload={
            "abstain": True,
            "reason": f"{variant} variant execution failed; excluded from comparison.",
            "findings": [],
        },
        draft_payload={"error": str(error)},
    )


def summarize_evaluation(records: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [record for record in records if record.get("status") == "complete"]
    metrics: dict[str, Any] = {
        "completed": len(completed),
        "failed": len(records) - len(completed),
        "reference_clear_issues": 0,
        "reference_likely_issues": 0,
        "reference_acceptable": 0,
        "reference_insufficient": 0,
    }
    for variant in ("legacy", "calibrated"):
        metrics[variant] = {
            "variant_failures": 0,
            "flagged_traces": 0,
            "active_flagged_traces": 0,
            "abstained_traces": 0,
            "resolved_findings": 0,
            "unknown_resolution_findings": 0,
            "false_positives": 0,
            "missed_issues": 0,
            "mean_evidence_quality": 0.0,
            "mean_codebase_grounding": 0.0,
            "mean_actionability": 0.0,
        }
    preferred = {"legacy": 0, "calibrated": 0, "tie": 0, "neither": 0}
    score_totals = {
        variant: {"evidence_quality": 0.0, "codebase_grounding": 0.0, "actionability": 0.0}
        for variant in ("legacy", "calibrated")
    }
    for record in completed:
        audit = record.get("audit") or {}
        classification = str((audit.get("reference_assessment") or {}).get("classification") or "")
        key = {
            "clear_issue": "reference_clear_issues",
            "likely_issue": "reference_likely_issues",
            "acceptable_behavior": "reference_acceptable",
            "insufficient_evidence": "reference_insufficient",
        }.get(classification)
        if key:
            metrics[key] += 1
        preferred_variant = str(audit.get("preferred_variant") or "neither")
        preferred[preferred_variant if preferred_variant in preferred else "neither"] += 1
        for variant in ("legacy", "calibrated"):
            metrics[variant]["variant_failures"] += int(
                variant in (record.get("variant_errors") or {})
            )
            decision = record.get(f"{variant}_decision") or {}
            variant_audit = audit.get(variant) or {}
            has_findings = isinstance(decision.get("findings"), list) and bool(
                decision["findings"]
            )
            if has_findings:
                metrics[variant]["flagged_traces"] += 1
                findings = [
                    finding for finding in decision["findings"] if isinstance(finding, dict)
                ]
                states = [str(finding.get("resolution_state") or "unknown") for finding in findings]
                metrics[variant]["resolved_findings"] += sum(
                    state == "resolved_in_trace" for state in states
                )
                metrics[variant]["unknown_resolution_findings"] += sum(
                    state == "unknown" for state in states
                )
                if any(state != "resolved_in_trace" for state in states):
                    metrics[variant]["active_flagged_traces"] += 1
            if decision.get("abstain") is True or not has_findings:
                metrics[variant]["abstained_traces"] += 1
            metrics[variant]["false_positives"] += int(
                has_findings
                and (
                    classification in {"acceptable_behavior", "insufficient_evidence"}
                    or bool(variant_audit.get("false_positive"))
                )
            )
            reference_issue = classification in {"clear_issue", "likely_issue"}
            metrics[variant]["missed_issues"] += int(
                reference_issue and (not has_findings or bool(variant_audit.get("missed_issue")))
            )
            for score_name in score_totals[variant]:
                score_totals[variant][score_name] += _score(variant_audit.get(score_name))
    denominator = max(1, len(completed))
    for variant in ("legacy", "calibrated"):
        for score_name, total in score_totals[variant].items():
            metrics[variant][f"mean_{score_name}"] = round(total / denominator, 3)
    metrics["preferred_variant"] = preferred
    return metrics


def _score(value: Any) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _normalize_audit_payload(
    payload: dict[str, Any],
    *,
    decisions: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    nested = payload.get("output_contract")
    normalized = dict(payload)
    if isinstance(nested, dict):
        for key in ("legacy", "calibrated", "preferred_variant"):
            if key not in normalized and key in nested:
                normalized[key] = nested[key]
    classification = str(
        (normalized.get("reference_assessment") or {}).get("classification") or ""
    )
    for variant, decision in (decisions or {}).items():
        findings = decision.get("findings")
        has_findings = isinstance(findings, list) and bool(findings)
        raw_variant_audit = normalized.get(variant)
        variant_audit = (
            dict(raw_variant_audit) if isinstance(raw_variant_audit, dict) else {}
        )
        if has_findings:
            if classification in {"acceptable_behavior", "insufficient_evidence"}:
                variant_audit["false_positive"] = True
        else:
            variant_audit["false_positive"] = False
            if classification in {"clear_issue", "likely_issue"}:
                variant_audit["missed_issue"] = True
        normalized[variant] = variant_audit
    return normalized
