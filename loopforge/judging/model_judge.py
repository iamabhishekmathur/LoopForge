"""Model-backed hypothesis judges."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Protocol
from urllib.request import Request, urlopen

from loopforge.models.behavior import AgentBehaviorMap, BehaviorContract
from loopforge.models.hypothesis import HypothesisFinding, JudgePlan
from loopforge.models.observed import ObservedAgentRun, ObservedStep


class HypothesisJudge(Protocol):
    def judge(
        self,
        run: ObservedAgentRun,
        plan: JudgePlan,
        behavior_map: AgentBehaviorMap,
        local_findings: list[HypothesisFinding],
        evidence_receipts: list[dict[str, Any]] | None = None,
    ) -> list[HypothesisFinding]:
        ...


@dataclass(frozen=True)
class LocalHypothesisJudge:
    """Offline judge that returns local findings unchanged."""

    def judge(
        self,
        run: ObservedAgentRun,
        plan: JudgePlan,
        behavior_map: AgentBehaviorMap,
        local_findings: list[HypothesisFinding],
        evidence_receipts: list[dict[str, Any]] | None = None,
    ) -> list[HypothesisFinding]:
        return local_findings


@dataclass(frozen=True)
class JsonFileHypothesisJudge:
    """Recorded model-judge fixture for deterministic qualification runs."""

    path: Path

    def judge(
        self,
        run: ObservedAgentRun,
        plan: JudgePlan,
        behavior_map: AgentBehaviorMap,
        local_findings: list[HypothesisFinding],
        evidence_receipts: list[dict[str, Any]] | None = None,
    ) -> list[HypothesisFinding]:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return _findings_from_judge_payload(
            payload,
            run,
            plan,
            behavior_map,
            local_findings,
            judge_name="json_file",
            extra_metadata={"judge_fixture": str(self.path)},
        )


@dataclass(frozen=True)
class OpenAICompatibleHypothesisJudge:
    """LLM-as-judge implementation for single-trace hypothesis judging."""

    endpoint: str
    model: str
    api_key_env: str = "OPENAI_API_KEY"
    timeout_seconds: float = 30.0
    max_payload_chars: int = 60000

    def judge(
        self,
        run: ObservedAgentRun,
        plan: JudgePlan,
        behavior_map: AgentBehaviorMap,
        local_findings: list[HypothesisFinding],
        evidence_receipts: list[dict[str, Any]] | None = None,
    ) -> list[HypothesisFinding]:
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise ValueError(f"missing API key environment variable: {self.api_key_env}")

        body = {
            "model": self.model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": HYPOTHESIS_JUDGE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": self._user_payload(
                        run,
                        plan,
                        behavior_map,
                        local_findings,
                        evidence_receipts=evidence_receipts,
                    ),
                },
            ],
        }
        request = Request(
            self.endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise ValueError(f"hypothesis judge request failed: {exc}") from exc

        judge_payload = _extract_chat_json(response_payload)
        return _findings_from_judge_payload(
            judge_payload,
            run,
            plan,
            behavior_map,
            local_findings,
            judge_name="openai_compatible",
            extra_metadata={"model": self.model, "endpoint": self.endpoint},
        )

    def _user_payload(
        self,
        run: ObservedAgentRun,
        plan: JudgePlan,
        behavior_map: AgentBehaviorMap,
        local_findings: list[HypothesisFinding],
        evidence_receipts: list[dict[str, Any]] | None = None,
    ) -> str:
        payload = build_hypothesis_judge_payload(
            run,
            plan,
            behavior_map,
            local_findings,
            evidence_receipts=evidence_receipts,
        )
        text = json.dumps(payload, indent=2, sort_keys=True)
        if len(text) <= self.max_payload_chars:
            return text
        truncated = {
            **payload,
            "observed_run": _compact_run(run, max_steps=12, max_text_chars=700),
            "behavior_map": _compact_behavior_map(behavior_map, max_contracts=25),
            "local_findings": [finding.to_dict() for finding in local_findings[:5]],
            "truncation": {
                "reason": "payload exceeded max_payload_chars",
                "max_payload_chars": self.max_payload_chars,
            },
        }
        return json.dumps(truncated, indent=2, sort_keys=True)[: self.max_payload_chars]


HYPOTHESIS_JUDGE_SYSTEM_PROMPT = """You are LoopForge's hypothesis judge for AI agent traces.

You are not grading against ground truth. You are judging whether the observed trace plausibly followed the user's intent and the codebase-derived agent harness. Use probabilistic judgment, cite trace evidence and codebase evidence, and prefer abstaining over weak accusations.

Evaluate intent alignment, tool or route selection, missing clarification, final-answer faithfulness, guardrail adherence, context use, Skill/tool contract adherence, and recovery from errors. A finding should be actionable for an agent engineer and should explain expected behavior, actual behavior, and the gap.

Return one JSON object. Do not include Markdown. Use the provided output contract. If evidence is too weak, return {"abstain": true, "reason": "..."}.
"""


HYPOTHESIS_JUDGE_OUTPUT_CONTRACT = {
    "abstain": "boolean optional; true when evidence is too weak",
    "findings": [
        {
            "finding_type": "intent_mismatch|tool_selection_mismatch|missing_clarification|final_answer_unfaithful|guardrail_gap|context_misuse|skill_contract_gap|observed_error|other",
            "title": "short finding title",
            "hypothesis": "expected vs actual behavior gap, phrased as a hypothesis",
            "severity": "low|medium|high",
            "confidence": "number from 0 to 1",
            "supporting_trace_evidence": "array of objects with kind and value",
            "supporting_codebase_evidence": "array of objects with contract_type/source_path/summary/confidence when available",
            "missing_evidence": "array of missing evidence fields that limit confidence",
            "recommended_next_action": "specific next action before patching",
            "expected_behavior": "what should have happened according to codebase/harness context",
            "actual_behavior": "what happened in the observed trace",
            "violated_contracts": "array of prompt/tool/skill/routing/guardrail/context contracts that appear violated",
            "false_positive_risks": "array of plausible reasons this hypothesis may be wrong",
        }
    ],
}


def build_hypothesis_judge_payload(
    run: ObservedAgentRun,
    plan: JudgePlan,
    behavior_map: AgentBehaviorMap,
    local_findings: list[HypothesisFinding],
    *,
    evidence_receipts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "task": (
            "Act as a third-party reviewer of one agent trace. Infer what should have "
            "happened from the codebase-derived behavior map, tool contracts, prompts, "
            "Skills, routing, context policy, and guardrails. Compare that against what "
            "actually happened in the observed trace. No ground truth is available, so "
            "produce only evidence-backed hypotheses or abstain."
        ),
        "output_contract": HYPOTHESIS_JUDGE_OUTPUT_CONTRACT,
        "observed_run": _compact_run(run),
        "judge_plan": plan.to_dict(),
        "behavior_map": _compact_behavior_map(behavior_map),
        "local_findings": [finding.to_dict() for finding in local_findings],
        "verified_evidence_receipts": evidence_receipts or [],
        "evidence_policy": {
            "raw_evidence_is_authoritative": True,
            "receipt_quotes_must_match_archived_source": True,
            "fallback_when_receipts_missing": "use observed_run compact fields and mark missing evidence explicitly",
        },
    }


def _findings_from_judge_payload(
    payload: dict[str, Any],
    run: ObservedAgentRun,
    plan: JudgePlan,
    behavior_map: AgentBehaviorMap,
    local_findings: list[HypothesisFinding],
    *,
    judge_name: str,
    extra_metadata: dict[str, Any] | None = None,
) -> list[HypothesisFinding]:
    if payload.get("abstain") is True:
        return _structural_local_findings(local_findings)
    raw_findings = payload.get("findings")
    if raw_findings is None and _looks_like_single_finding(payload):
        raw_findings = [payload]
    if not isinstance(raw_findings, list):
        raise ValueError("hypothesis judge response must contain a findings array or abstain")

    findings = []
    for raw in raw_findings:
        if not isinstance(raw, dict):
            continue
        finding = _finding_from_raw(
            raw,
            run,
            plan,
            behavior_map,
            judge_name=judge_name,
            extra_metadata=extra_metadata or {},
        )
        if finding:
            findings.append(finding)
    if findings:
        return _structural_local_findings(local_findings) + findings
    return _structural_local_findings(local_findings)


def _finding_from_raw(
    raw: dict[str, Any],
    run: ObservedAgentRun,
    plan: JudgePlan,
    behavior_map: AgentBehaviorMap,
    *,
    judge_name: str,
    extra_metadata: dict[str, Any],
) -> HypothesisFinding | None:
    confidence = _clamp_float(raw.get("confidence"), default=0.0)
    if confidence <= 0:
        return None
    finding_type = str(raw.get("finding_type") or raw.get("type") or "model_hypothesis")
    title = str(raw.get("title") or finding_type.replace("_", " ").title())
    raw_codebase_evidence = raw.get("supporting_codebase_evidence")
    model_supplied_codebase_evidence = (
        isinstance(raw_codebase_evidence, list) and bool(raw_codebase_evidence)
    )
    supporting_codebase_evidence = raw_codebase_evidence
    if not isinstance(supporting_codebase_evidence, list):
        supporting_codebase_evidence = _codebase_evidence(behavior_map)
    raw_trace_evidence = raw.get("supporting_trace_evidence")
    model_supplied_trace_evidence = isinstance(raw_trace_evidence, list) and bool(raw_trace_evidence)
    supporting_trace_evidence = raw_trace_evidence
    if not isinstance(supporting_trace_evidence, list):
        supporting_trace_evidence = _default_trace_evidence(run)
    metadata = {
        "judge": judge_name,
        "judge_plan_id": plan.plan_id,
        "expected_behavior": raw.get("expected_behavior"),
        "actual_behavior": raw.get("actual_behavior"),
        "violated_contracts": raw.get("violated_contracts") or [],
        "false_positive_risks": raw.get("false_positive_risks") or [],
        "model_supplied_trace_evidence": model_supplied_trace_evidence,
        "model_supplied_codebase_evidence": model_supplied_codebase_evidence,
        **extra_metadata,
    }
    return HypothesisFinding(
        finding_id=_finding_id(run.trace_id, finding_type, title),
        trace_id=str(raw.get("trace_id") or run.trace_id),
        finding_type=finding_type,
        title=title,
        hypothesis=str(raw.get("hypothesis") or "Model judge identified a possible behavior gap."),
        severity=_severity(raw.get("severity")),
        confidence=confidence,
        judgeability_score=run.judgeability_score,
        supporting_trace_evidence=supporting_trace_evidence,
        supporting_codebase_evidence=supporting_codebase_evidence,
        missing_evidence=[str(item) for item in raw.get("missing_evidence") or run.missing_evidence],
        recommended_next_action=str(
            raw.get("recommended_next_action")
            or "Review the cited trace and codebase evidence before drafting a patch."
        ),
        metadata=metadata,
    )


def _extract_chat_json(response_payload: dict[str, Any]) -> dict[str, Any]:
    choices = response_payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    parsed = json.loads(content)
                    if isinstance(parsed, dict):
                        return parsed
    if isinstance(response_payload.get("findings"), list) or response_payload.get("abstain") is True:
        return response_payload
    raise ValueError("hypothesis judge response did not contain JSON content")


def _structural_local_findings(findings: list[HypothesisFinding]) -> list[HypothesisFinding]:
    return [
        finding
        for finding in findings
        if finding.finding_type in {"insufficient_trace_coverage", "observed_error"}
    ]


def _looks_like_single_finding(payload: dict[str, Any]) -> bool:
    return "finding_type" in payload or "hypothesis" in payload or "title" in payload


def _compact_run(
    run: ObservedAgentRun,
    *,
    max_steps: int = 30,
    max_text_chars: int = 1400,
) -> dict[str, Any]:
    return {
        **run.to_dict(),
        "user_intent": _trim(run.user_intent, max_text_chars),
        "final_response": _trim(run.final_response, max_text_chars),
        "steps": [_compact_step(step, max_text_chars=max_text_chars) for step in run.steps[:max_steps]],
    }


def _compact_step(step: ObservedStep, *, max_text_chars: int) -> dict[str, Any]:
    return {
        **step.to_dict(),
        "input_preview": _trim(step.input_preview, max_text_chars),
        "output_preview": _trim(step.output_preview, max_text_chars),
    }


def _compact_behavior_map(
    behavior_map: AgentBehaviorMap,
    *,
    max_contracts: int = 50,
) -> dict[str, Any]:
    return {
        **behavior_map.to_dict(),
        "contracts": [
            _compact_contract(contract) for contract in behavior_map.contracts[:max_contracts]
        ],
        "tool_catalog": behavior_map.tool_catalog[:50],
    }


def _compact_contract(contract: BehaviorContract) -> dict[str, Any]:
    return {
        "contract_id": contract.contract_id,
        "contract_type": contract.contract_type,
        "source_path": contract.source_path,
        "summary": contract.summary,
        "confidence": contract.confidence,
        "metadata": {
            "tool_name": contract.metadata.get("tool_name"),
            "side_effect_class": contract.metadata.get("side_effect_class"),
            "signals": contract.metadata.get("signals"),
        },
    }


def _default_trace_evidence(run: ObservedAgentRun) -> list[dict[str, Any]]:
    return [
        {"kind": "user_intent", "value": run.user_intent},
        {"kind": "final_response", "value": run.final_response},
        {"kind": "tool_calls", "value": run.tool_calls},
        {"kind": "available_evidence", "value": run.available_evidence},
    ]


def _codebase_evidence(behavior_map: AgentBehaviorMap) -> list[dict[str, Any]]:
    return [
        {
            "contract_type": contract.contract_type,
            "source_path": contract.source_path,
            "summary": contract.summary,
            "confidence": contract.confidence,
        }
        for contract in behavior_map.contracts[:5]
    ]


def _trim(value: str | None, max_chars: int) -> str | None:
    if value is None or len(value) <= max_chars:
        return value
    return value[:max_chars] + "..."


def _clamp_float(value: Any, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return round(max(0.0, min(1.0, parsed)), 2)


def _severity(value: Any) -> str:
    text = str(value or "low").lower()
    return text if text in {"low", "medium", "high"} else "low"


def _finding_id(trace_id: str, finding_type: str, title: str) -> str:
    digest = hashlib.sha256(f"{trace_id}:{finding_type}:{title}".encode("utf-8")).hexdigest()[:12]
    return f"HF-{digest}"
