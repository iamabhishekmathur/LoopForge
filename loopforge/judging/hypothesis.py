"""Local hypothesis judge.

This is deliberately conservative: it does not pretend to have ground truth.
It creates findings for insufficient trace coverage, observed errors, and
high-signal heuristic gaps. A live LLM judge can later replace or augment this
implementation while preserving the same finding model.
"""

from __future__ import annotations

import hashlib
import re

from loopforge.models.behavior import AgentBehaviorMap
from loopforge.models.hypothesis import HypothesisFinding, JudgePlan
from loopforge.models.observed import ObservedAgentRun


def judge_hypotheses(
    run: ObservedAgentRun,
    plan: JudgePlan,
    behavior_map: AgentBehaviorMap,
) -> list[HypothesisFinding]:
    findings: list[HypothesisFinding] = []
    missing_core = [item for item in ("user_intent", "final_response") if item in run.missing_evidence]
    if missing_core:
        findings.append(_trace_coverage_finding(run, plan, behavior_map, missing_core))
    if run.errors:
        findings.append(_error_recovery_finding(run, plan, behavior_map))
    if run.user_intent and run.steps:
        mismatch = _possible_intent_gap(run)
        if mismatch:
            findings.append(_intent_gap_finding(run, plan, behavior_map, mismatch))
    return findings


def _trace_coverage_finding(
    run: ObservedAgentRun,
    plan: JudgePlan,
    behavior_map: AgentBehaviorMap,
    missing_core: list[str],
) -> HypothesisFinding:
    return HypothesisFinding(
        finding_id=_finding_id(run.trace_id, "insufficient_trace_coverage"),
        trace_id=run.trace_id,
        finding_type="insufficient_trace_coverage",
        title="Trace is missing evidence required for behavior judging",
        hypothesis=(
            "LoopForge can see execution activity, but the trace is missing "
            f"{', '.join(missing_core)}. Without those fields, hypothesis judges cannot "
            "reliably assess user-intent alignment, tool choice, or final-answer faithfulness."
        ),
        severity="medium",
        confidence=0.88,
        judgeability_score=run.judgeability_score,
        supporting_trace_evidence=[
            {"kind": "available_evidence", "value": run.available_evidence},
            {"kind": "missing_evidence", "value": run.missing_evidence},
            {"kind": "span_count", "value": run.metadata.get("span_count")},
        ],
        supporting_codebase_evidence=_codebase_evidence(behavior_map),
        missing_evidence=run.missing_evidence,
        recommended_next_action=(
            "Instrument root agent traces to include initial user input, selected route/tool, "
            "guardrail verdicts when present, and final assistant response."
        ),
        metadata={"judge_plan_id": plan.plan_id},
    )


def _error_recovery_finding(
    run: ObservedAgentRun,
    plan: JudgePlan,
    behavior_map: AgentBehaviorMap,
) -> HypothesisFinding:
    return HypothesisFinding(
        finding_id=_finding_id(run.trace_id, "observed_error"),
        trace_id=run.trace_id,
        finding_type="observed_error",
        title="Trace contains errored execution steps",
        hypothesis=(
            "The trace contains one or more errored steps. Without final response and "
            "recovery context, LoopForge cannot tell whether the agent recovered cleanly."
        ),
        severity="medium",
        confidence=0.74,
        judgeability_score=run.judgeability_score,
        supporting_trace_evidence=[
            {"kind": "errors", "value": run.errors[:5]},
            {"kind": "steps", "value": [step.to_dict() for step in run.steps if step.error][:3]},
        ],
        supporting_codebase_evidence=_codebase_evidence(behavior_map),
        missing_evidence=run.missing_evidence,
        recommended_next_action=(
            "Review errored spans and ensure the trace records retry decisions and the final user-visible outcome."
        ),
        metadata={"judge_plan_id": plan.plan_id},
    )


def _intent_gap_finding(
    run: ObservedAgentRun,
    plan: JudgePlan,
    behavior_map: AgentBehaviorMap,
    mismatch: dict[str, object],
) -> HypothesisFinding:
    return HypothesisFinding(
        finding_id=_finding_id(run.trace_id, "possible_intent_mismatch"),
        trace_id=run.trace_id,
        finding_type="possible_intent_mismatch",
        title="Observed execution may not address the user intent",
        hypothesis=(
            "The user intent and observed execution share weak lexical overlap. This is a hypothesis, "
            "not ground truth; a domain-specific LLM judge should inspect the full prompt, tool output, "
            "and final answer before recommending a patch."
        ),
        severity="low",
        confidence=float(mismatch["confidence"]),
        judgeability_score=run.judgeability_score,
        supporting_trace_evidence=[
            {"kind": "user_intent", "value": run.user_intent},
            {"kind": "observed_terms", "value": mismatch["observed_terms"]},
            {"kind": "intent_terms", "value": mismatch["intent_terms"]},
        ],
        supporting_codebase_evidence=_codebase_evidence(behavior_map),
        missing_evidence=run.missing_evidence,
        recommended_next_action=(
            "Run a codebase-aware LLM judge over this trace and inspect whether the chosen tool/result "
            "was a reasonable response to the request."
        ),
        metadata={"judge_plan_id": plan.plan_id, "overlap": mismatch["overlap"]},
    )


def _possible_intent_gap(run: ObservedAgentRun) -> dict[str, object] | None:
    if not run.user_intent:
        return None
    intent_terms = _terms(run.user_intent)
    observed_text = " ".join(
        f"{step.name} {step.input_preview} {step.output_preview}" for step in run.steps
    )
    observed_terms = _terms(observed_text)
    if len(intent_terms) < 3 or len(observed_terms) < 3:
        return None
    overlap_terms = sorted(intent_terms & observed_terms)
    overlap = len(overlap_terms) / max(1, len(intent_terms))
    if overlap >= 0.18:
        return None
    return {
        "intent_terms": sorted(intent_terms)[:20],
        "observed_terms": sorted(observed_terms)[:20],
        "overlap": round(overlap, 3),
        "confidence": 0.58,
    }


def _terms(text: str) -> set[str]:
    stop = {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "what",
        "when",
        "where",
        "show",
        "tell",
        "give",
        "please",
    }
    return {
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_]{2,}", text.lower())
        if token not in stop
    }


def _codebase_evidence(behavior_map: AgentBehaviorMap) -> list[dict[str, object]]:
    evidence = []
    for contract in behavior_map.contracts[:5]:
        evidence.append(
            {
                "contract_type": contract.contract_type,
                "source_path": contract.source_path,
                "summary": contract.summary,
                "confidence": contract.confidence,
            }
        )
    return evidence


def _finding_id(trace_id: str, finding_type: str) -> str:
    digest = hashlib.sha256(f"{trace_id}:{finding_type}".encode("utf-8")).hexdigest()[:12]
    return f"HF-{digest}"

