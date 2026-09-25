"""Model-backed hypothesis judges."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Protocol
from urllib.request import Request, urlopen

from loopforge.judging.context import (
    contract_excerpt,
    select_relevant_contracts,
    select_trajectory_steps,
)
from loopforge.models.behavior import AgentBehaviorMap, BehaviorContract
from loopforge.models.hypothesis import HypothesisFinding, JudgePlan
from loopforge.models.observed import ObservedAgentRun, ObservedStep
from loopforge.privacy.redaction import sanitize_for_external_llm


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
class JudgeDecision:
    payload: dict[str, Any]
    interpretation: dict[str, Any] | None = None
    draft_payload: dict[str, Any] | None = None
    sanitized_replacement_count: int = 0
    sanitized_replacement_types: dict[str, int] | None = None
    critic_applied: bool = False


@dataclass(frozen=True)
class OpenAICompatibleHypothesisJudge:
    """LLM-as-judge implementation for single-trace hypothesis judging."""

    endpoint: str
    model: str
    api_key_env: str = "OPENAI_API_KEY"
    timeout_seconds: float = 30.0
    max_payload_chars: int = 60000
    payload_variant: str = "calibrated"
    critic_enabled: bool = False
    review_model: str | None = None
    max_output_tokens: int = 6000

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

        decision = self.decide(
            run,
            plan,
            behavior_map,
            local_findings,
            evidence_receipts=evidence_receipts,
        )
        return _findings_from_judge_payload(
            decision.payload,
            run,
            plan,
            behavior_map,
            local_findings,
            judge_name="openai_compatible",
            extra_metadata={
                "model": self.model,
                "endpoint": self.endpoint,
                "payload_variant": self.payload_variant,
                "critic_applied": decision.critic_applied,
                "sanitized_replacement_count": decision.sanitized_replacement_count,
                "sanitized_replacement_types": decision.sanitized_replacement_types or {},
            },
        )

    def decide(
        self,
        run: ObservedAgentRun,
        plan: JudgePlan,
        behavior_map: AgentBehaviorMap,
        local_findings: list[HypothesisFinding],
        evidence_receipts: list[dict[str, Any]] | None = None,
    ) -> JudgeDecision:
        """Return the model's raw structured decision for calibration and auditing."""

        payload = build_hypothesis_judge_payload(
            run,
            plan,
            behavior_map,
            local_findings,
            evidence_receipts=evidence_receipts,
            variant=self.payload_variant,
        )
        sanitized = sanitize_for_external_llm(payload)
        evidence_packet = dict(sanitized.value)
        interpretation: dict[str, Any] | None = None
        if self.payload_variant != "legacy":
            resolver_packet = build_trace_resolution_packet(evidence_packet)
            intent_contract = self._request_json(
                INTENT_CONTRACT_SYSTEM_PROMPT,
                self._serialize_payload(
                    {
                        "task": "Infer the minimum sufficient answer contract for this turn.",
                        "output_contract": INTENT_CONTRACT_OUTPUT_CONTRACT,
                        "observed_user_intent": resolver_packet.get("observed_user_intent"),
                        "current_turn_candidates": resolver_packet.get(
                            "current_turn_candidates"
                        ),
                    }
                ),
                model=self.review_model,
                operation="intent_contract_resolver",
                max_output_tokens=1200,
            )
            interpretation = self._request_json(
                TRACE_RESOLVER_SYSTEM_PROMPT,
                self._serialize_payload(
                    {
                        "task": (
                            "Resolve the actual user-authored intent and terminal outcome from this "
                            "multi-agent trace before issue judging."
                        ),
                        "output_contract": {
                            key: value
                            for key, value in TRACE_RESOLVER_OUTPUT_CONTRACT.items()
                            if key != "answer_requirements"
                        },
                        "frozen_answer_requirements": intent_contract.get(
                            "answer_requirements"
                        )
                        or [],
                        "evidence_packet": resolver_packet,
                    }
                ),
                model=self.review_model,
                operation="trace_resolver",
                max_output_tokens=2500,
            )
            interpretation["answer_requirements"] = intent_contract.get(
                "answer_requirements"
            ) or []
            evidence_packet["model_resolved_trace"] = interpretation
        payload_text = self._serialize_payload(evidence_packet)
        response_draft = self._request_json(
            HYPOTHESIS_JUDGE_SYSTEM_PROMPT,
            payload_text,
            operation="response_judge",
        )
        coverage_draft: dict[str, Any] | None = None
        if self.payload_variant != "legacy":
            coverage_payload = {
                "task": "Evaluate each frozen required answer criterion against the outcome.",
                "evidence_packet": build_judge_verification_packet(evidence_packet),
                "output_contract": HYPOTHESIS_JUDGE_OUTPUT_CONTRACT,
            }
            coverage_draft = self._request_json(
                REQUIREMENT_COVERAGE_JUDGE_PROMPT,
                self._serialize_payload(coverage_payload),
                operation="requirement_coverage_judge",
            )
            coverage_draft = _enforce_finding_scope(coverage_draft, "agent_response")
            response_draft = _merge_same_scope_decisions(
                response_draft,
                coverage_draft,
                "agent_response",
            )
        latent_draft: dict[str, Any] | None = None
        if self.payload_variant != "legacy":
            latent_draft = self._request_json(
                LATENT_FAILURE_JUDGE_SYSTEM_PROMPT,
                payload_text,
                operation="latent_failure_judge",
            )
        response_draft = _enforce_finding_scope(response_draft, "agent_response")
        if latent_draft is not None:
            latent_draft = _enforce_finding_scope(latent_draft, "latent_system_failure")
        draft = _merge_judge_decisions(response_draft, latent_draft)
        draft_record = {
            "response_judge": response_draft,
            "requirement_coverage_judge": coverage_draft,
            "latent_failure_judge": latent_draft,
            "merged": draft,
        }
        if not self.critic_enabled:
            return JudgeDecision(
                payload=draft,
                interpretation=interpretation,
                draft_payload=draft_record,
                sanitized_replacement_count=sanitized.replacement_count,
                sanitized_replacement_types=sanitized.replacement_types,
            )

        review_packet = build_judge_review_packet(evidence_packet, interpretation=interpretation)
        reviewed_decisions: list[tuple[dict[str, Any], str]] = []
        critic_replacement_count = 0
        critic_replacement_types: dict[str, int] = {}
        for specialist_decision, scope in (
            (response_draft, "agent_response"),
            (latent_draft, "latent_system_failure"),
        ):
            if specialist_decision is None:
                continue
            critic_payload = {
                "task": (
                    "Audit this specialist draft against the supplied evidence. Reject speculative "
                    "findings, unsupported contract claims, and expected control flow. Preserve "
                    "supported issues useful to an agent engineer."
                ),
                "review_scope": scope,
                "evidence_packet": review_packet,
                "draft_decision": specialist_decision,
                "output_contract": HYPOTHESIS_JUDGE_OUTPUT_CONTRACT,
            }
            critic_sanitized = sanitize_for_external_llm(critic_payload)
            reviewed_specialist = self._request_json(
                HYPOTHESIS_JUDGE_CRITIC_PROMPT,
                self._serialize_payload(critic_sanitized.value),
                model=self.review_model,
                operation=f"{scope}_critic",
            )
            reviewed_specialist = _normalize_model_decision(
                _enforce_finding_scope(reviewed_specialist, scope)
            )
            reviewed_decisions.append((reviewed_specialist, scope))
            critic_replacement_count += critic_sanitized.replacement_count
            for kind, count in critic_sanitized.replacement_types.items():
                critic_replacement_types[kind] = critic_replacement_types.get(kind, 0) + count

        reviewed = _merge_judge_decisions(
            next(
                (decision for decision, scope in reviewed_decisions if scope == "agent_response"),
                {"abstain": True, "reason": "Response-quality review was unavailable."},
            ),
            next(
                (
                    decision
                    for decision, scope in reviewed_decisions
                    if scope == "latent_system_failure"
                ),
                None,
            ),
        )
        arbiter_payload = {
            "task": (
                "Make the final precision decision over the separately reviewed findings. Keep "
                "only findings that identify an actual behavior or system gap."
            ),
            "evidence_packet": review_packet,
            "reviewed_decision": reviewed,
            "output_contract": HYPOTHESIS_JUDGE_OUTPUT_CONTRACT,
        }
        arbiter_sanitized = sanitize_for_external_llm(arbiter_payload)
        reviewed = self._request_json(
            HYPOTHESIS_JUDGE_ARBITER_PROMPT,
            self._serialize_payload(arbiter_sanitized.value),
            model=self.review_model,
            operation="finding_arbiter",
        )
        reviewed = _normalize_model_decision(reviewed)
        verification_decisions: list[tuple[dict[str, Any], str]] = []
        verifier_replacement_count = 0
        verifier_replacement_types: dict[str, int] = {}
        for scope, verifier_prompt in (
            ("agent_response", HYPOTHESIS_JUDGE_VERIFIER_PROMPT),
            ("latent_system_failure", HYPOTHESIS_LATENT_VERIFIER_PROMPT),
        ):
            candidate_decision = _decision_for_scope(reviewed, scope)
            if candidate_decision.get("abstain") is True:
                verification_decisions.append((candidate_decision, scope))
                continue
            verifier_payload = {
                "task": (
                    "Independently verify these final candidate findings for semantic entailment "
                    "and actual impact. Remove every candidate that does not survive."
                ),
                "verification_scope": scope,
                "evidence_packet": build_judge_verification_packet(review_packet),
                "candidate_decision": candidate_decision,
                "output_contract": HYPOTHESIS_JUDGE_OUTPUT_CONTRACT,
            }
            verifier_sanitized = sanitize_for_external_llm(verifier_payload)
            scoped_verified = self._request_json(
                verifier_prompt,
                self._serialize_payload(verifier_sanitized.value),
                model=self.review_model,
                operation=f"{scope}_verifier",
            )
            scoped_verified = _normalize_model_decision(
                _enforce_finding_scope(scoped_verified, scope)
            )
            verification_decisions.append((scoped_verified, scope))
            verifier_replacement_count += verifier_sanitized.replacement_count
            for kind, count in verifier_sanitized.replacement_types.items():
                verifier_replacement_types[kind] = (
                    verifier_replacement_types.get(kind, 0) + count
                )
        verified = _merge_judge_decisions(
            next(
                (
                    decision
                    for decision, scope in verification_decisions
                    if scope == "agent_response"
                ),
                {"abstain": True, "reason": "No response candidates required verification."},
            ),
            next(
                (
                    decision
                    for decision, scope in verification_decisions
                    if scope == "latent_system_failure"
                ),
                None,
            ),
        )
        verified = _enforce_answer_requirement_references(verified, interpretation)
        draft_record["specialist_reviews"] = {
            scope: decision for decision, scope in reviewed_decisions
        }
        draft_record["final_arbiter"] = reviewed
        draft_record["final_verifier"] = {
            scope: decision for decision, scope in verification_decisions
        }
        reviewed = verified
        critic_replacement_count += (
            arbiter_sanitized.replacement_count + verifier_replacement_count
        )
        combined_review_types = dict(arbiter_sanitized.replacement_types)
        for kind, count in verifier_replacement_types.items():
            combined_review_types[kind] = combined_review_types.get(kind, 0) + count
        for kind, count in combined_review_types.items():
            critic_replacement_types[kind] = critic_replacement_types.get(kind, 0) + count
        replacement_types = dict(sanitized.replacement_types)
        for kind, count in critic_replacement_types.items():
            replacement_types[kind] = replacement_types.get(kind, 0) + count
        return JudgeDecision(
            payload=reviewed,
            interpretation=interpretation,
            draft_payload=draft_record,
            sanitized_replacement_count=(
                sanitized.replacement_count + critic_replacement_count
            ),
            sanitized_replacement_types=replacement_types,
            critic_applied=True,
        )

    def _request_json(
        self,
        system_prompt: str,
        user_payload: str,
        *,
        model: str | None = None,
        operation: str = "hypothesis_judge",
        max_output_tokens: int | None = None,
    ) -> dict[str, Any]:
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise ValueError(f"missing API key environment variable: {self.api_key_env}")
        body = {
            "model": model or self.model,
            "temperature": 0.2,
            "max_tokens": max_output_tokens or self.max_output_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_payload},
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
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    response_payload = json.loads(response.read().decode("utf-8"))
                return _extract_chat_json(response_payload)
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
        raise ValueError(f"{operation} request failed: {last_error}") from last_error

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
            variant=self.payload_variant,
        )
        sanitized = sanitize_for_external_llm(payload)
        return self._serialize_payload(sanitized.value)

    def _serialize_payload(self, payload: dict[str, Any]) -> str:
        text = json.dumps(payload, indent=2, sort_keys=True)
        if len(text) <= self.max_payload_chars:
            return text
        truncated = dict(payload)
        observed = dict(truncated.get("observed_run") or {})
        observed["steps"] = list(observed.get("steps") or [])[:16]
        behavior = dict(truncated.get("behavior_map") or {})
        behavior["contracts"] = list(behavior.get("contracts") or [])[:12]
        truncated.update({
            "observed_run": observed,
            "behavior_map": behavior,
            "local_findings": list(truncated.get("local_findings") or [])[:5],
            "truncation": {
                "reason": "payload exceeded max_payload_chars",
                "max_payload_chars": self.max_payload_chars,
            },
        })
        for string_limit in (900, 500, 240):
            compacted = _truncate_payload_strings(truncated, max_chars=string_limit)
            text = json.dumps(compacted, indent=2, sort_keys=True)
            if len(text) <= self.max_payload_chars:
                return text
        emergency = {
            "task": truncated.get("task"),
            "output_contract": truncated.get("output_contract"),
            "observed_run": _truncate_payload_strings(observed, max_chars=180),
            "behavior_map": _truncate_payload_strings(behavior, max_chars=180),
            "local_findings": _truncate_payload_strings(
                truncated.get("local_findings") or [], max_chars=180
            ),
            "truncation": truncated["truncation"],
        }
        text = json.dumps(emergency, indent=2, sort_keys=True)
        if len(text) > self.max_payload_chars:
            emergency["observed_run"]["steps"] = list(
                emergency["observed_run"].get("steps") or []
            )[:8]
            emergency["behavior_map"]["contracts"] = list(
                emergency["behavior_map"].get("contracts") or []
            )[:6]
            emergency["behavior_map"]["tool_catalog"] = list(
                emergency["behavior_map"].get("tool_catalog") or []
            )[:10]
            text = json.dumps(emergency, indent=2, sort_keys=True)
        if len(text) > self.max_payload_chars:
            raise ValueError(
                f"hypothesis judge payload cannot fit max_payload_chars={self.max_payload_chars}"
            )
        return text


HYPOTHESIS_JUDGE_SYSTEM_PROMPT = """You are LoopForge's response-quality judge for AI agent traces.

You are not grading against ground truth. You are judging whether the observed trace plausibly followed the user's intent and the codebase-derived agent harness. Use probabilistic judgment, cite trace evidence and codebase evidence, and prefer abstaining over weak accusations.

Evaluate only the outer agent response: intent alignment, tool or route selection, missing clarification, final-answer faithfulness, guardrail adherence, context use, Skill/tool contract adherence, and recovery from errors. Another specialist evaluates latent system failures. Every finding from this pass must use finding_scope=agent_response and describe an actual gap. It must cite at least one required model_resolved_trace.answer_requirements ID in violated_requirement_ids. Optional requirements and merely useful context cannot support a finding. A finding should be actionable for an agent engineer and should explain expected behavior, actual behavior, and the gap.

First validate that the extracted intent, final response, and selected trajectory events are a coherent representation of the trace. The evidence packet can contain multiple plausible response candidates. Do not manufacture a failure from an extraction ambiguity. Distinguish expected pauses, clarifications, and multi-stage UI responses from defects.

For every proposed finding, actively search for the strongest evidence that the behavior was acceptable. A finding is valid only when the observed gap survives that challenge and cites the supplied evidence. A statement that the agent behaved correctly or that no gap exists is never a finding; abstain instead. Do not claim that a codebase contract says something unless its excerpt supports the claim.

Return one JSON object. Do not include Markdown. Use the provided output contract. If evidence is too weak or behavior appears acceptable, return {"abstain": true, "reason": "..."}.
"""


REQUIREMENT_COVERAGE_JUDGE_PROMPT = """You are LoopForge's requirement-coverage specialist for AI-agent traces.

Evaluate each model_resolved_trace.answer_requirements item marked required against the resolved terminal outcome, observed final response, terminal tool actions, and cited artifacts. Treat fulfillment_timing as authoritative. Do not flag after_interaction_or_execution requirements during a clarification or expected control-flow pause. For a complete outcome, classify each required criterion internally as satisfied, unsatisfied, or unknown.

Create an agent_response finding only for an explicitly unsatisfied criterion. Cite its requirement_id in violated_requirement_ids. Strict output constraints such as word count, required fields, forbidden language, or exact formatting are enforceable when the terminal output is visible. A promise to perform work later does not satisfy a criterion requiring execution or reporting now. Conversely, when the trace confirms a table, chart, linked artifact, patch, publication, or structured action containing the deliverable, treat it as satisfied even if the plain-text response is brief. When the relevant UI or artifact content is absent or ambiguous, classify it unknown and abstain rather than alleging omission.

Do not assess latent system failures and do not invent requirements. Return only JSON matching the supplied finding contract. If no required criterion is explicitly unsatisfied, abstain with a concise reason.
"""


LATENT_FAILURE_JUDGE_SYSTEM_PROMPT = """You are LoopForge's latent-system-failure miner for AI agent traces.

Do not grade whether the outer agent responded well. Inspect tool results, generated queries, artifact probes, evaluator outputs, degraded-mode signals, diagnostics, and terminal structured actions for evidence that any underlying agent, model, prompt, Skill, tool, routing rule, data pipeline, guardrail, or orchestration component behaved incorrectly or materially below its intended function.

A diagnostic agent can behave perfectly while proving that another component failed. That proven underlying defect is exactly what you must report. For example, a risk model falling back to hard-coded coefficients because its training pipeline produced one class is a latent system failure even when fallback control flow worked and the outer agent correctly diagnosed it. Distinguish an intentional harmless fallback from a degradation that makes product output unreliable. Require evidence and state false-positive risks.

Missing guardrail verdicts or other absent observability are insufficient evidence, not a latent failure, unless a supplied contract explicitly requires that event to be emitted and the complete trace proves it was omitted.

Every finding must use finding_scope=latent_system_failure. Claims that no issue exists are never findings. If no supported latent failure exists, return {"abstain": true, "reason": "..."}. Return only JSON using the supplied output contract.

Set resolution_state for every finding. Use resolved_in_trace when the trace itself applies and confirms the repair, mitigated_in_trace when it only reduces or contains the impact, unresolved when the defect remains, and unknown when the trace cannot establish current state. A repaired historical failure can remain useful evidence, but its next action should verify or monitor the repair rather than propose the same patch again.
"""


INTENT_CONTRACT_SYSTEM_PROMPT = """You define the minimum sufficient answer contract for one current user turn.

Use only observed_user_intent and current_turn_candidates. You do not have the later trace outcome and must not invent requirements based on facts the agent might discover. Split requirements into atomic criteria. Mark a criterion required only when the user explicitly asks for it or it is logically necessary to answer the request; mark useful extra context optional. Assign fulfillment_timing: immediate for a direct answer that should be returned now, after_interaction_or_execution for an analysis, generated artifact, mission run, or other task that may legitimately require tools or user inputs, and before_side_effect only for a clarification or confirmation logically required before an action. A bare analysis or mission name is a request to perform that task, not a request to explain its name, unless the user asks what it is. When the current turn already contains an affirmative answer to a prior confirmation question, do not require the agent to ask for or echo that confirmation again. For a ranked, selected, filtered, or scored subset, the eligible selection population is the operational denominator. A broader raw or ineligible population is optional unless the user explicitly asks for the full raw universe. Do not require caveats, diagnostics, explanations, or remediation that the current request did not ask for.

Return at most five requirements. Use stable IDs R1 through R5. Return JSON only.
"""


INTENT_CONTRACT_OUTPUT_CONTRACT = {
    "answer_requirements": [
        {
            "requirement_id": "R1",
            "criterion": "one atomic minimum-sufficient answer criterion",
            "necessity": "required|optional",
            "fulfillment_timing": "immediate|after_interaction_or_execution|before_side_effect",
            "basis": "short explanation grounded only in the current request",
        }
    ]
}


TRACE_RESOLVER_SYSTEM_PROMPT = """You resolve evidence in complex AI-agent traces before quality judging.

Identify the actual current-turn user-authored request, excluding system prompts, locked context metadata, tool instructions, and prior-turn text. Treat current_turn_candidates as the highest-provenance source for the current request. Other user_intent_candidates may represent a carried goal or prior turns; do not merge them into the current request unless the current turn explicitly refers back to them. Identify the terminal user-facing response or terminal tool action, excluding planning narration such as 'I will check' or 'let me verify'. In multi-agent traces, a structured answer, Diagnosis, ReviewDiagnosisDraft, patch, publication, or other terminal tool call supersedes earlier narration and can be the outcome even when no plain-text answer follows. When terminal_tool_actions contains Diagnosis, treat the last Diagnosis outcome_summary as the terminal outcome unless later evidence explicitly supersedes it. Prefer a terminal tool action's outcome_summary over an intermediate observed_run.final_response.

Do not judge whether the behavior is good yet. The supplied frozen_answer_requirements were inferred from the request alone; do not add, remove, broaden, or reinterpret them based on facts discovered later. Report evidence ambiguity explicitly. Summarize rather than copying code, prompts, or tool payloads. Keep current_turn_request, carried_goal, and resolved_user_intent under 800 characters each; resolved_terminal_outcome under 1,600 characters; each supporting quote under 500 characters; and return at most 6 supporting evidence items and 5 ambiguities. Return every key in the supplied output contract, including outcome_kind, outcome_complete, supporting_evidence, and ambiguities. Return JSON only.
"""


TRACE_RESOLVER_OUTPUT_CONTRACT = {
    "current_turn_request": "string or null",
    "carried_goal": "string or null",
    "resolved_user_intent": "string or null",
    "answer_requirements": [
        {
            "requirement_id": "R1",
            "criterion": "minimum sufficient answer criterion",
            "necessity": "required|optional",
            "basis": "current request or relevant selection semantics",
        }
    ],
    "resolved_terminal_outcome": "string or structured summary or null",
    "outcome_kind": "user_facing_answer|clarification|tool_action|control_flow_pause|missing",
    "outcome_complete": "boolean",
    "supporting_evidence": [
        {"kind": "candidate|step|tool_action", "reference": "string", "quote": "string"}
    ],
    "ambiguities": ["string"],
}


HYPOTHESIS_JUDGE_CRITIC_PROMPT = """You are the skeptical second-pass reviewer for an AI-agent trace judge.

Independently compare each draft finding with the sanitized trace and codebase evidence. Review only the supplied review_scope. Remove findings caused by parser ambiguity, incomplete UI rendering context, expected clarification, expected control flow, unsupported assumptions, or findings that merely say the agent behaved correctly. The model_resolved_trace terminal outcome supersedes an intermediate observed_run.final_response unless the resolution itself lists a material ambiguity. Do not retain an agent_response finding that complains about an intermediate sentence when a later Diagnosis, answer, patch, or publication action completed the intent. Remove any finding outside review_scope. For latent_system_failure review, ignore whether the outer agent answered correctly: preserve a supported underlying data, model, prompt, tool, routing, guardrail, or orchestration defect revealed by the trace. Ambiguity in the outer final answer is not counterevidence to a separately proven latent failure. Require explicit expected behavior, actual behavior, trace evidence, codebase evidence, false-positive risks, and a concrete next action. Prefer abstention only when no remaining finding would justify asking an engineering team to investigate.

Return only the same JSON output contract supplied in the request. Every abstention must include a concise reason explaining why the behavior is acceptable or the evidence is insufficient. Do not include Markdown.
"""


HYPOTHESIS_JUDGE_ARBITER_PROMPT = """You are LoopForge's final precision arbiter for probabilistic AI-agent trace findings.

Review the already criticized findings against the compact evidence packet. Keep a finding only if expected_behavior and actual_behavior describe a material, evidence-backed gap. A finding that says the agent or component behaved correctly is not a finding. A user's desired product state being absent is not itself a system failure when the agent accurately reports the state and follows a documented capability boundary. A recommendation for a new feature, broader capability, or better documentation is not evidence that the existing harness failed.

Do not expand the user's request after the fact. For a ranked, filtered, or scored subset, the eligible or scoreable population is the operational denominator. Do not require an additional raw or ineligible population unless the user explicitly asked for it or a supplied contract requires it.

Every agent_response finding must cite violated_requirement_ids that exist in model_resolved_trace.answer_requirements and are marked required. Remove findings based only on optional context. Latent-system findings do not use answer requirement IDs.

Preserve and verify resolution_state. If the same trace applies and confirms a repair, mark the historical failure resolved_in_trace; do not describe it as still active or recommend applying the same repair again.

For agent_response findings, model_resolved_trace and its terminal structured outcome supersede ambiguous or intermediate response text unless the resolver records a material ambiguity. For latent_system_failure findings, independently preserve a demonstrated defect in a model, data pipeline, prompt, tool, Skill, routing rule, guardrail, or orchestration component even if the outer agent diagnosed it correctly. Intentional fallback control flow may still expose a latent failure when the triggering condition materially degrades product output, but the evidence must identify the degraded component and consequence.

Do not create new findings. You may tighten the language or remove unsupported claims from reviewed findings. If none survives, abstain with a concise reason. Return only JSON matching the supplied output contract.
"""


HYPOTHESIS_JUDGE_VERIFIER_PROMPT = """You are an independent high-precision verifier for AI-agent trace findings.

Check each supplied candidate against the compact evidence without trusting the candidate's wording. Do not create new findings. Keep only candidates with a material expected-versus-actual gap that is semantically entailed by cited evidence. Evaluate semantic coverage before presentation preference. If a response states "X of Y," then Y is an explicit denominator; reject any claim that the denominator is absent or insufficiently explicit. For ranked, filtered, or scored results, the eligible or scoreable population is the operational denominator. Reject a finding that demands an additional raw or ineligible population unless the user explicitly requested it or a supplied contract requires it. More generally, if the actual response contains the requested answer or fulfills the expected behavior, reject complaints that it was not explicit enough, had weak lexical overlap, could have been clearer, or should have offered extra UX guidance. Reject findings whose own actual_behavior says the agent acted correctly, plausibly aligned with intent, or followed a documented capability boundary.

For every agent_response candidate, validate violated_requirement_ids against model_resolved_trace.answer_requirements. Reject it when no cited requirement exists, the requirement is optional, or the terminal outcome satisfies it. Latent-system candidates do not require these IDs.

Verify resolution_state from the trace. A finding repaired and confirmed within the same trace must be resolved_in_trace and must not carry a recommendation to repeat the completed patch.

For latent_system_failure candidates, judge the underlying component separately from the outer response. An intentional fallback does not make the underlying condition acceptable when the component was expected to train or operate normally and instead produced materially degraded or uncalibrated output. Preserve that failure when the trace proves both the degradation and its mechanism, even if the outer agent diagnosed or disclosed it correctly.

Return the surviving findings in the same schema without changing their scope. If none survives, abstain and explain why. Return JSON only.
"""


HYPOTHESIS_LATENT_VERIFIER_PROMPT = """You are an independent high-precision verifier for latent system failures revealed by AI-agent traces.

Review only latent_system_failure candidates. Do not evaluate whether the outer agent answered the user well, and do not apply answer requirement IDs. Keep a candidate only when the trace and codebase evidence identify a material defect or degradation in an underlying model, data pipeline, prompt, tool, Skill, routing rule, guardrail, or orchestration component. An intentional fallback does not make its triggering condition acceptable when a component expected to train or operate normally instead emits materially degraded or uncalibrated output. Preserve a proven latent failure even when the outer agent diagnosed or disclosed it correctly. Reject product suggestions, expected control flow, and unsupported mechanism guesses.

Verify resolution_state and do not recommend repeating a repair completed in the same trace. Do not create new findings. Return surviving findings in the same schema with finding_scope=latent_system_failure. If none survives, abstain and explain why. Return JSON only.
"""


HYPOTHESIS_JUDGE_OUTPUT_CONTRACT = {
    "abstain": "boolean optional; true when evidence is too weak",
    "findings": [
        {
            "finding_type": "intent_mismatch|tool_selection_mismatch|missing_clarification|final_answer_unfaithful|guardrail_gap|context_misuse|skill_contract_gap|data_pipeline_gap|degraded_model_output|orchestration_gap|observed_error|other",
            "finding_scope": "agent_response|latent_system_failure",
            "resolution_state": "unresolved|mitigated_in_trace|resolved_in_trace|unknown",
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
            "violated_requirement_ids": "required answer requirement IDs; agent_response only",
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
    variant: str = "calibrated",
) -> dict[str, Any]:
    selected_contracts = (
        behavior_map.contracts
        if variant == "legacy"
        else select_relevant_contracts(run, behavior_map)
    )
    return {
        "task": (
            "Act as a third-party reviewer of one agent trace. Infer what should have "
            "happened from the codebase-derived behavior map, tool contracts, prompts, "
            "Skills, routing, context policy, and guardrails. Compare that against what "
            "actually happened in the observed trace. No ground truth is available, so "
            "produce only evidence-backed hypotheses or abstain."
        ),
        "output_contract": HYPOTHESIS_JUDGE_OUTPUT_CONTRACT,
        "observed_run": _compact_run(run, variant=variant),
        "judge_plan": plan.to_dict(),
        "behavior_map": _compact_behavior_map(
            behavior_map,
            contracts=selected_contracts,
            include_excerpts=variant != "legacy",
        ),
        "local_findings": [finding.to_dict() for finding in local_findings],
        "verified_evidence_receipts": evidence_receipts or [],
        "evidence_policy": {
            "raw_evidence_is_authoritative": True,
            "receipt_quotes_must_match_archived_source": True,
            "fallback_when_receipts_missing": "use observed_run compact fields and mark missing evidence explicitly",
        },
        "calibration_policy": {
            "variant": variant,
            "acceptable_behavior_is_not_a_finding": True,
            "challenge_each_finding_with_counterevidence": variant != "legacy",
            "extraction_ambiguity_requires_abstention": variant != "legacy",
        },
    }


def build_judge_review_packet(
    evidence_packet: dict[str, Any],
    *,
    interpretation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a compact, loss-resistant evidence capsule for criticism and adjudication."""

    observed = dict(evidence_packet.get("observed_run") or {})
    metadata = dict(observed.get("metadata") or {})
    behavior = dict(evidence_packet.get("behavior_map") or {})
    resolved = interpretation or evidence_packet.get("model_resolved_trace")
    return {
        "model_resolved_trace": resolved,
        "observed_run": {
            "trace_id": observed.get("trace_id"),
            "user_intent": observed.get("user_intent"),
            "final_response": observed.get("final_response"),
            "errors": observed.get("errors") or [],
            "control_flow_events": observed.get("control_flow_events") or [],
            "tool_calls": observed.get("tool_calls") or [],
            "steps": list(observed.get("steps") or [])[:30],
            "metadata": {
                "current_turn_candidates": metadata.get("current_turn_candidates") or [],
                "user_intent_candidates": metadata.get("user_intent_candidates") or [],
                "final_response_candidates": metadata.get("final_response_candidates") or [],
                "tool_actions": list(metadata.get("tool_actions") or [])[-12:],
                "trace_coverage": metadata.get("trace_coverage"),
            },
        },
        "behavior_map": {
            "contracts": list(behavior.get("contracts") or [])[:12],
            "tool_catalog": list(behavior.get("tool_catalog") or [])[:20],
            "graph_summary": behavior.get("graph_summary"),
        },
        "local_findings": list(evidence_packet.get("local_findings") or [])[:5],
        "evidence_policy": evidence_packet.get("evidence_policy") or {},
    }


def build_trace_resolution_packet(evidence_packet: dict[str, Any]) -> dict[str, Any]:
    """Keep trace resolution focused on temporal and message provenance."""

    observed = dict(evidence_packet.get("observed_run") or {})
    metadata = dict(observed.get("metadata") or {})
    return {
        "trace_id": observed.get("trace_id"),
        "observed_user_intent": observed.get("user_intent"),
        "observed_final_response": observed.get("final_response"),
        "current_turn_candidates": metadata.get("current_turn_candidates") or [],
        "user_intent_candidates": metadata.get("user_intent_candidates") or [],
        "final_response_candidates": metadata.get("final_response_candidates") or [],
        "terminal_tool_actions": list(metadata.get("tool_actions") or [])[-12:],
        "trajectory_steps": list(observed.get("steps") or [])[-16:],
        "control_flow_events": observed.get("control_flow_events") or [],
    }


def build_judge_verification_packet(review_packet: dict[str, Any]) -> dict[str, Any]:
    """Focus final verification on semantic coverage and directly cited evidence."""

    observed = dict(review_packet.get("observed_run") or {})
    metadata = dict(observed.get("metadata") or {})
    behavior = dict(review_packet.get("behavior_map") or {})
    return {
        "model_resolved_trace": review_packet.get("model_resolved_trace"),
        "observed_run": {
            "trace_id": observed.get("trace_id"),
            "user_intent": observed.get("user_intent"),
            "final_response": observed.get("final_response"),
            "errors": observed.get("errors") or [],
            "metadata": {
                "current_turn_candidates": metadata.get("current_turn_candidates") or [],
                "tool_actions": list(metadata.get("tool_actions") or [])[-8:],
            },
        },
        "behavior_map": {
            "contracts": list(behavior.get("contracts") or [])[:6],
            "tool_catalog": list(behavior.get("tool_catalog") or [])[:12],
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
        "finding_scope": raw.get("finding_scope") or "agent_response",
        "resolution_state": raw.get("resolution_state") or "unknown",
        "violated_contracts": raw.get("violated_contracts") or [],
        "violated_requirement_ids": raw.get("violated_requirement_ids") or [],
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
                    parsed = _normalize_model_json_value(_loads_model_json(content))
                    if isinstance(parsed, dict):
                        return parsed
    if isinstance(response_payload.get("findings"), list) or response_payload.get("abstain") is True:
        return response_payload
    raise ValueError("hypothesis judge response did not contain JSON content")


def _loads_model_json(content: str) -> Any:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        repaired = _escape_invalid_json_string_backslashes(content)
        if repaired == content:
            raise
        return json.loads(repaired)


def _escape_invalid_json_string_backslashes(content: str) -> str:
    """Repair literal code backslashes without changing valid JSON escapes."""

    output: list[str] = []
    index = 0
    in_string = False
    hex_digits = set("0123456789abcdefABCDEF")
    while index < len(content):
        char = content[index]
        if char == '"':
            in_string = not in_string
            output.append(char)
            index += 1
            continue
        if not in_string or char != "\\":
            output.append(char)
            index += 1
            continue
        if index + 1 >= len(content):
            output.append("\\\\")
            index += 1
            continue
        escaped = content[index + 1]
        if escaped in '"\\/bfnrt':
            output.extend((char, escaped))
            index += 2
            continue
        if escaped == "u" and index + 5 < len(content):
            digits = content[index + 2 : index + 6]
            if len(digits) == 4 and all(digit in hex_digits for digit in digits):
                output.append(content[index : index + 6])
                index += 6
                continue
        output.append("\\\\")
        index += 1
    return "".join(output)


def _normalize_model_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _normalize_model_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_model_json_value(item) for item in value]
    if isinstance(value, str):
        return "".join(
            char if ord(char) >= 32 or char in "\n\r\t" else " " for char in value
        )
    return value


def _merge_judge_decisions(
    response_decision: dict[str, Any],
    latent_decision: dict[str, Any] | None,
) -> dict[str, Any]:
    if latent_decision is None:
        return response_decision
    findings: list[dict[str, Any]] = []
    for decision, default_scope in (
        (response_decision, "agent_response"),
        (latent_decision, "latent_system_failure"),
    ):
        raw_findings = decision.get("findings")
        if not isinstance(raw_findings, list):
            continue
        for finding in raw_findings:
            if not isinstance(finding, dict):
                continue
            normalized = dict(finding)
            normalized.setdefault("finding_scope", default_scope)
            findings.append(normalized)
    if findings:
        return {"abstain": False, "findings": findings}
    reasons = [
        str(decision.get("reason") or decision.get("abstain_reason") or "").strip()
        for decision in (response_decision, latent_decision)
        if isinstance(decision, dict)
    ]
    return {
        "abstain": True,
        "reason": " ".join(reason for reason in reasons if reason)
        or "Neither specialist found an evidence-backed issue.",
    }


def _merge_same_scope_decisions(
    first: dict[str, Any],
    second: dict[str, Any],
    scope: str,
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    for decision in (first, second):
        for finding in decision.get("findings") or []:
            if isinstance(finding, dict):
                findings.append({**finding, "finding_scope": scope})
    if findings:
        return {"abstain": False, "findings": findings}
    reasons = [
        str(decision.get("reason") or "").strip()
        for decision in (first, second)
        if isinstance(decision, dict)
    ]
    return {
        "abstain": True,
        "reason": " ".join(reason for reason in reasons if reason)
        or "Neither response specialist found an explicit requirement violation.",
    }


def _enforce_finding_scope(payload: dict[str, Any], scope: str) -> dict[str, Any]:
    """Keep specialist routing metadata authoritative without deciding issue validity."""

    normalized = dict(payload)
    raw_findings = payload.get("findings")
    if not isinstance(raw_findings, list):
        return normalized
    findings: list[dict[str, Any]] = []
    for finding in raw_findings:
        if not isinstance(finding, dict):
            continue
        findings.append({**finding, "finding_scope": scope})
    normalized["findings"] = findings
    return normalized


def _decision_for_scope(payload: dict[str, Any], scope: str) -> dict[str, Any]:
    findings = [
        finding
        for finding in payload.get("findings") or []
        if isinstance(finding, dict) and finding.get("finding_scope") == scope
    ]
    if findings:
        return {"abstain": False, "findings": findings}
    return {"abstain": True, "reason": f"No {scope} candidates require verification."}


def _enforce_answer_requirement_references(
    payload: dict[str, Any],
    interpretation: dict[str, Any] | None,
) -> dict[str, Any]:
    required = {
        str(requirement.get("requirement_id")): requirement
        for requirement in (interpretation or {}).get("answer_requirements") or []
        if isinstance(requirement, dict)
        and requirement.get("necessity") == "required"
        and requirement.get("requirement_id")
    }
    findings = payload.get("findings")
    if not isinstance(findings, list):
        return payload
    accepted: list[dict[str, Any]] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        if finding.get("finding_scope") != "agent_response":
            accepted.append({**finding, "violated_requirement_ids": []})
            continue
        cited_ids = {
            str(item) for item in finding.get("violated_requirement_ids") or [] if item
        }
        cited_required = [required[item] for item in cited_ids if item in required]
        if not cited_required:
            continue
        if finding.get("finding_type") == "missing_clarification" and not any(
            requirement.get("fulfillment_timing") == "before_side_effect"
            for requirement in cited_required
        ):
            continue
        outcome_kind = str((interpretation or {}).get("outcome_kind") or "")
        outcome_complete = bool((interpretation or {}).get("outcome_complete"))
        if (
            finding.get("finding_type") in {"intent_mismatch", "final_answer_unfaithful"}
            and outcome_kind in {"clarification", "control_flow_pause"}
            and not outcome_complete
            and all(
                requirement.get("fulfillment_timing") == "after_interaction_or_execution"
                for requirement in cited_required
            )
        ):
            continue
        accepted.append(finding)
    if accepted:
        return {**payload, "abstain": False, "findings": accepted}
    return {
        "abstain": True,
        "reason": "No finding violated a required pre-answer acceptance criterion.",
        "findings": [],
    }


def _normalize_model_decision(payload: dict[str, Any]) -> dict[str, Any]:
    raw_findings = payload.get("findings")
    if not isinstance(raw_findings, list):
        return payload
    valid: list[dict[str, Any]] = []
    for finding in raw_findings:
        if not isinstance(finding, dict):
            continue
        try:
            confidence = float(finding.get("confidence"))
        except (TypeError, ValueError):
            continue
        if not 0 < confidence <= 1:
            continue
        if finding.get("finding_scope") not in {"agent_response", "latent_system_failure"}:
            continue
        if finding.get("finding_scope") == "latent_system_failure" and finding.get(
            "finding_type"
        ) not in {
            "data_pipeline_gap",
            "degraded_model_output",
            "orchestration_gap",
            "guardrail_gap",
            "skill_contract_gap",
            "observed_error",
            "other",
        }:
            continue
        if finding.get("finding_scope") == "agent_response" and not isinstance(
            finding.get("violated_requirement_ids"), list
        ):
            continue
        if finding.get("finding_scope") == "agent_response" and not finding.get(
            "violated_requirement_ids"
        ):
            continue
        if finding.get("resolution_state") not in {
            "unresolved",
            "mitigated_in_trace",
            "resolved_in_trace",
            "unknown",
        }:
            finding = {**finding, "resolution_state": "unknown"}
        required_text = (
            finding.get("hypothesis"),
            finding.get("expected_behavior"),
            finding.get("actual_behavior"),
            finding.get("recommended_next_action"),
        )
        if not all(isinstance(value, str) and value.strip() for value in required_text):
            continue
        if not isinstance(finding.get("supporting_trace_evidence"), list):
            continue
        if not isinstance(finding.get("supporting_codebase_evidence"), list):
            continue
        valid.append(finding)
    if valid:
        return {**payload, "abstain": False, "findings": valid}
    return {
        "abstain": True,
        "reason": payload.get("reason")
        or payload.get("abstain_reason")
        or "No finding satisfied the required evidence contract.",
        "findings": [],
    }


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
    variant: str = "calibrated",
) -> dict[str, Any]:
    steps = (
        run.steps[:max_steps]
        if variant == "legacy"
        else select_trajectory_steps(run, limit=max_steps)
    )
    return {
        **run.to_dict(),
        "user_intent": _trim(run.user_intent, max_text_chars),
        "final_response": _trim(run.final_response, max_text_chars),
        "steps": [_compact_step(step, max_text_chars=max_text_chars) for step in steps],
        "trajectory_selection": {
            "total_steps": len(run.steps),
            "selected_steps": len(steps),
            "strategy": "prefix_only" if variant == "legacy" else "boundary_and_salience",
        },
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
    contracts: list[BehaviorContract] | None = None,
    include_excerpts: bool = False,
) -> dict[str, Any]:
    selected = (contracts if contracts is not None else behavior_map.contracts)[:max_contracts]
    return {
        **behavior_map.to_dict(),
        "contracts": [
            _compact_contract(contract, include_excerpt=include_excerpts) for contract in selected
        ],
        "tool_catalog": behavior_map.tool_catalog[:50],
        "contract_selection": {
            "total_contracts": len(behavior_map.contracts),
            "selected_contracts": len(selected),
            "strategy": "trace_relevance" if contracts is not None else "prefix_only",
        },
    }


def _compact_contract(
    contract: BehaviorContract,
    *,
    include_excerpt: bool = False,
) -> dict[str, Any]:
    payload = {
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
    if include_excerpt:
        payload["evidence_excerpt"] = contract_excerpt(contract)
    return payload


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


def _truncate_payload_strings(value: Any, *, max_chars: int) -> Any:
    if isinstance(value, str):
        return value if len(value) <= max_chars else value[:max_chars] + "..."
    if isinstance(value, list):
        return [_truncate_payload_strings(item, max_chars=max_chars) for item in value]
    if isinstance(value, dict):
        return {
            key: _truncate_payload_strings(item, max_chars=max_chars)
            for key, item in value.items()
        }
    return value


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
