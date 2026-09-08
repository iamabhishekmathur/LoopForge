"""Resolution planning for mined issues."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from loopforge.models.issue import Issue
from loopforge.models.resolution import ResolutionPlan
from loopforge.paths import LOCAL_DIR


def build_resolution_plan(
    issue: Issue,
    *,
    artifacts: list[dict[str, Any]],
    evals: list[dict[str, Any]] | None = None,
    validations: list[dict[str, Any]] | None = None,
    patches: list[dict[str, Any]] | None = None,
    gate_reports: list[dict[str, Any]] | None = None,
) -> ResolutionPlan:
    evals = evals or []
    validations = validations or []
    patches = patches or []
    gate_reports = gate_reports or []
    contradictions = _contradictions(issue, artifacts)
    rankings = _root_cause_rankings(issue, artifacts, contradictions)
    blockers = _gate_blockers(gate_reports)
    evidence_needed = _evidence_needed(issue, validations, contradictions, blockers)
    actions = _candidate_actions(issue, artifacts, evals, patches, validations, contradictions)
    next_action = _recommended_next_action(rankings, blockers, validations)
    return ResolutionPlan(
        plan_id=f"RESOLVE-{issue.issue_id.removeprefix('ISSUE-')}",
        issue_id=issue.issue_id,
        status="blocked" if blockers else "drafted",
        generated_at=datetime.now(timezone.utc).isoformat(),
        observed_failure=_observed_failure(issue),
        evidence_trace_ids=issue.evidence_trace_ids,
        contradictions=contradictions,
        root_cause_rankings=rankings,
        recommended_next_action=next_action,
        candidate_actions=actions,
        gate_blockers=blockers,
        evidence_needed=evidence_needed,
        artifacts=artifacts,
        metadata={
            "eval_count": len(evals),
            "validation_count": len(validations),
            "patch_count": len(patches),
            "gate_report_count": len(gate_reports),
        },
    )


def write_resolution_plan(root: Path, plan: ResolutionPlan) -> dict[str, Path]:
    directory = root / LOCAL_DIR / "resolutions"
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / f"{plan.plan_id}.json"
    markdown_path = directory / f"{plan.plan_id}.md"
    json_path.write_text(json.dumps(plan.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(resolution_plan_markdown(plan), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}


def resolution_plan_markdown(plan: ResolutionPlan) -> str:
    return f"""# {plan.plan_id}: Resolution Plan For {plan.issue_id}

Status: `{plan.status}`
Generated: `{plan.generated_at}`

## Observed Failure

{plan.observed_failure}

## Evidence

- Traces: {_comma_code(plan.evidence_trace_ids)}

## Contradictions

{_dict_bullets(plan.contradictions, "label", "explanation")}

## Ranked Root Causes

{_ranked_causes(plan.root_cause_rankings)}

## Recommended Next Action

{plan.recommended_next_action}

## Candidate Actions

{_candidate_action_lines(plan.candidate_actions)}

## Gate Blockers

{_gate_blocker_lines(plan.gate_blockers)}

## Evidence Needed

{_simple_bullets(plan.evidence_needed)}
"""


def _observed_failure(issue: Issue) -> str:
    tools = issue.metadata.get("implicated_tools", [])
    tool_text = ", ".join(f"`{tool}`" for tool in tools) or "a side-effecting tool"
    return (
        f"LoopForge observed {tool_text} being called in failing traces without an "
        "approval or confirmation span before the side effect."
    )


def _contradictions(issue: Issue, artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    contradictions: list[dict[str, Any]] = []
    tools = set(str(tool) for tool in issue.metadata.get("implicated_tools", []))
    permission_artifacts = [
        artifact
        for artifact in artifacts
        if artifact.get("artifact_type") == "permission_policy"
        and (
            tools.intersection(set(str(tool) for tool in artifact.get("metadata", {}).get("tools", [])))
            or "governs" in str(artifact.get("reason", "")).lower()
        )
    ]
    has_missing_confirmation = any(
        hypothesis.get("label") == "missing_confirmation_contract"
        for hypothesis in issue.root_cause_hypotheses
        if isinstance(hypothesis, dict)
    )
    if permission_artifacts and has_missing_confirmation:
        contradictions.append(
            {
                "label": "policy_requires_confirmation_but_trace_lacks_approval",
                "severity": "high",
                "explanation": (
                    "A permission policy is linked to the implicated tool, but the failing traces "
                    "show no approval span before the destructive call. This points first to "
                    "runtime enforcement or instrumentation, not just prompt wording."
                ),
                "artifact_paths": [str(artifact.get("path")) for artifact in permission_artifacts],
            }
        )
    return contradictions


def _root_cause_rankings(
    issue: Issue,
    artifacts: list[dict[str, Any]],
    contradictions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    has_policy_contradiction = any(
        item.get("label") == "policy_requires_confirmation_but_trace_lacks_approval"
        for item in contradictions
    )
    has_tool_artifact = any(artifact.get("artifact_type") == "tool_definition" for artifact in artifacts)
    has_prompt_artifact = any(artifact.get("artifact_type") == "system_prompt" for artifact in artifacts)

    rankings = []
    if has_policy_contradiction:
        rankings.append(
            {
                "label": "runtime_enforcement_gap",
                "confidence": 0.93,
                "explanation": (
                    "The policy appears to require confirmation, yet the runtime allowed the "
                    "side-effecting tool call without observed approval."
                ),
            }
        )
        rankings.append(
            {
                "label": "trace_instrumentation_gap",
                "confidence": 0.72,
                "explanation": (
                    "Confirmation might exist in application state but not be emitted as a "
                    "`human_approval` span, which would make the trace look unsafe."
                ),
            }
        )
    if has_tool_artifact:
        rankings.append(
            {
                "label": "tool_contract_gap",
                "confidence": 0.56 if has_policy_contradiction else 0.78,
                "explanation": (
                    "The tool description may not make the confirmation requirement clear enough "
                    "for the agent or tool router."
                ),
            }
        )
    if has_prompt_artifact:
        rankings.append(
            {
                "label": "prompt_contract_gap",
                "confidence": 0.48 if has_policy_contradiction else 0.68,
                "explanation": (
                    "The system instructions may permit the agent to treat exploratory cancellation "
                    "language as authorization."
                ),
            }
        )
    if not rankings:
        rankings.extend(issue.root_cause_hypotheses)
    return sorted(rankings, key=lambda item: float(item.get("confidence", 0)), reverse=True)


def _candidate_actions(
    issue: Issue,
    artifacts: list[dict[str, Any]],
    evals: list[dict[str, Any]],
    patches: list[dict[str, Any]],
    validations: list[dict[str, Any]],
    contradictions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    tools = ", ".join(str(tool) for tool in issue.metadata.get("implicated_tools", [])) or "the implicated tool"
    if contradictions:
        actions.append(
            {
                "label": "inspect_runtime_enforcement",
                "priority": 1,
                "owner": "agent engineer",
                "status": "needs_human_review",
                "action": (
                    f"Trace the runtime call path for {tools} and verify the permission policy is "
                    "checked immediately before tool execution."
                ),
            }
        )
        actions.append(
            {
                "label": "verify_approval_span_instrumentation",
                "priority": 2,
                "owner": "agent engineer",
                "status": "needs_human_review",
                "action": (
                    "Confirm that successful approvals emit a `human_approval` span before the "
                    "destructive tool call."
                ),
            }
        )
    for patch in patches:
        actions.append(
            {
                "label": "review_candidate_patch",
                "priority": 3,
                "owner": "reviewer",
                "status": patch.get("status", "drafted"),
                "action": f"Review `{patch.get('patch_id')}` and its diff preview before applying it.",
            }
        )
    if evals:
        evaluator_needs_evidence = _has_unvalidated_evaluator(validations)
        actions.append(
            {
                "label": "strengthen_eval_evidence" if evaluator_needs_evidence else "keep_evaluator_as_gate",
                "priority": 4,
                "owner": "agent engineer",
                "status": "needed" if evaluator_needs_evidence else "ready",
                "action": _eval_action(evaluator_needs_evidence),
            }
        )
    if not actions:
        actions.append(
            {
                "label": "collect_more_trace_evidence",
                "priority": 1,
                "owner": "agent engineer",
                "status": "needed",
                "action": "Collect more traces with tool calls, approvals, errors, and feedback.",
            }
        )
    return actions


def _gate_blockers(gate_reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for report in gate_reports:
        for suite in report.get("suites", []):
            if not isinstance(suite, dict) or suite.get("status") not in {"reject", "error"}:
                continue
            blockers.append(
                {
                    "gate_report_id": report.get("gate_report_id"),
                    "suite": suite.get("name"),
                    "status": suite.get("status"),
                    "failed_cases": suite.get("failed_cases", []),
                }
            )
    return blockers


def _evidence_needed(
    issue: Issue,
    validations: list[dict[str, Any]],
    contradictions: list[dict[str, Any]],
    blockers: list[dict[str, Any]],
) -> list[str]:
    needed = []
    if contradictions:
        needed.append("Runtime evidence that the permission policy is enforced before the tool call.")
        needed.append("Trace evidence showing whether confirmed flows emit `human_approval` spans.")
    if _has_unvalidated_evaluator(validations):
        needed.append("More labeled positive and negative examples for evaluator validation.")
    if blockers:
        blocked_suites = ", ".join(str(item.get("suite")) for item in blockers)
        needed.append(f"Gate blocker resolution for: {blocked_suites}.")
    if len(issue.evidence_trace_ids) < 5:
        needed.append("Additional recurrence evidence; fewer than 5 evidence traces are currently linked.")
    return needed


def _recommended_next_action(
    rankings: list[dict[str, Any]],
    blockers: list[dict[str, Any]],
    validations: list[dict[str, Any]],
) -> str:
    if blockers:
        blocker_names = ", ".join(str(item.get("suite")) for item in blockers)
        return f"Do not open a PR yet. Resolve gate blockers first: {blocker_names}."
    if rankings and rankings[0].get("label") == "runtime_enforcement_gap":
        return (
            "Inspect the runtime tool-execution path before accepting a wording-only patch; "
            "the linked policy already indicates confirmation is required."
        )
    if _has_unvalidated_evaluator(validations):
        return "Strengthen evaluator validation evidence before using the patch as a blocking release gate."
    return "Review the highest-ranked candidate action and run gates before drafting a PR."


def _has_unvalidated_evaluator(validations: list[dict[str, Any]]) -> bool:
    if not validations:
        return True
    return any(validation.get("blocking_gate_eligible") is not True for validation in validations)


def _eval_action(needs_evidence: bool) -> str:
    if needs_evidence:
        return (
            "Add or collect more positive and negative examples so the drafted evaluator "
            "can become blocking-eligible."
        )
    return "Keep the validated evaluator attached to gates so recurrence is caught before release."


def _comma_code(items: list[str]) -> str:
    return ", ".join(f"`{item}`" for item in items) if items else "None"


def _dict_bullets(items: list[dict[str, Any]], title_key: str, body_key: str) -> str:
    if not items:
        return "- None"
    return "\n".join(
        f"- `{item.get(title_key, 'unknown')}`: {item.get(body_key, '')}"
        for item in items
    )


def _ranked_causes(items: list[dict[str, Any]]) -> str:
    if not items:
        return "- None"
    lines = []
    for item in items:
        confidence = float(item.get("confidence", 0))
        lines.append(
            f"- `{item.get('label', 'unknown')}` ({confidence:.2f}): {item.get('explanation', '')}"
        )
    return "\n".join(lines)


def _candidate_action_lines(items: list[dict[str, Any]]) -> str:
    if not items:
        return "- None"
    lines = []
    for item in sorted(items, key=lambda action: int(action.get("priority", 99))):
        lines.append(
            f"- P{item.get('priority', '?')} `{item.get('label', 'unknown')}` "
            f"[{item.get('status', 'unknown')}]: {item.get('action', '')}"
        )
    return "\n".join(lines)


def _gate_blocker_lines(items: list[dict[str, Any]]) -> str:
    if not items:
        return "- None"
    lines = []
    for item in items:
        failed_cases = item.get("failed_cases") or []
        detail = "; ".join(str(case) for case in failed_cases) if failed_cases else "no details"
        lines.append(
            f"- `{item.get('suite', 'unknown')}` from `{item.get('gate_report_id')}`: {detail}"
        )
    return "\n".join(lines)


def _simple_bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- None"
