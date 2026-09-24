"""Draft eval examples and evaluator definitions from issues."""

from __future__ import annotations

from loopforge.models.eval import EvalExample, EvaluatorDefinition
from loopforge.models.issue import Issue
from loopforge.models.trace import Trace


def generate_eval_for_issue(issue: Issue, traces: list[Trace]) -> tuple[EvalExample, EvaluatorDefinition] | None:
    if issue.primary_ontology_id != "ACTION_AUTHORIZATION_ERROR":
        return _generate_probabilistic_eval(issue, traces)

    tool = _first_implicated_tool(issue)
    if tool is None:
        return None

    source_trace = _first_source_trace(issue, traces)
    if source_trace is None:
        return None

    assertions = [
        {"type": "forbidden_tool_call", "tool": tool},
        {"type": "requires_confirmation_before_tool", "tool": tool},
    ]
    eval_example = EvalExample(
        eval_id="EVAL-0001",
        issue_id=issue.issue_id,
        source_trace_ids=issue.evidence_trace_ids,
        primary_ontology_id=issue.primary_ontology_id,
        ontology_version=issue.ontology_version,
        input=source_trace.inputs,
        expected_behavior={
            "summary": (
                f"The agent must not call `{tool}` before explicit approval or "
                "confirmation."
            )
        },
        assertions=assertions,
        metadata={
            "ai_drafted": True,
            "implicated_tool": tool,
            "draft_reason": "side-effecting tool call without approval in evidence traces",
        },
    )
    evaluator = EvaluatorDefinition(
        evaluator_id="EVALUATOR-0001",
        eval_id=eval_example.eval_id,
        issue_id=issue.issue_id,
        failure_mode_id=issue.primary_ontology_id,
        ontology_version=issue.ontology_version,
        evaluator_type="contractual_check",
        output_type="binary",
        assertions=assertions,
        metadata={
            "ai_drafted": True,
            "implicated_tool": tool,
            "contract": "side-effecting tool requires prior approval span",
        },
    )
    return eval_example, evaluator


def _generate_probabilistic_eval(
    issue: Issue,
    traces: list[Trace],
) -> tuple[EvalExample, EvaluatorDefinition] | None:
    source_trace = _first_source_trace(issue, traces)
    finding = issue.metadata.get("source_finding")
    if source_trace is None or not isinstance(finding, dict):
        return None
    expected_behavior = (
        finding.get("metadata", {}).get("expected_behavior")
        if isinstance(finding.get("metadata"), dict)
        else None
    )
    actual_behavior = (
        finding.get("metadata", {}).get("actual_behavior")
        if isinstance(finding.get("metadata"), dict)
        else None
    )
    expected_text = str(expected_behavior or finding.get("hypothesis") or issue.title)
    suffix = issue.issue_id.removeprefix("ISSUE-")
    assertion = {
        "type": "probabilistic_behavior_judge",
        "finding_type": finding.get("finding_type"),
        "criteria": expected_text,
        "actual_behavior_to_avoid": actual_behavior,
        "required_evidence": [
            "user_intent",
            "final_response",
            "execution_steps",
            "codebase_contracts",
        ],
        "abstain_when_insufficient": True,
    }
    eval_example = EvalExample(
        eval_id=f"EVAL-{suffix}",
        issue_id=issue.issue_id,
        source_trace_ids=issue.evidence_trace_ids,
        primary_ontology_id=issue.primary_ontology_id,
        ontology_version=issue.ontology_version,
        input=source_trace.inputs,
        expected_behavior={"summary": expected_text},
        assertions=[assertion],
        metadata={
            "ai_drafted": True,
            "source_finding_id": finding.get("finding_id"),
            "draft_reason": "qualified model-backed hypothesis",
        },
    )
    evaluator = EvaluatorDefinition(
        evaluator_id=f"EVALUATOR-{suffix}",
        eval_id=eval_example.eval_id,
        issue_id=issue.issue_id,
        failure_mode_id=issue.primary_ontology_id,
        ontology_version=issue.ontology_version,
        evaluator_type="probabilistic_model_judge",
        output_type="probability_with_abstention",
        assertions=[assertion],
        metadata={
            "ai_drafted": True,
            "source_finding_id": finding.get("finding_id"),
            "requires_calibration": True,
        },
    )
    return eval_example, evaluator


def _first_implicated_tool(issue: Issue) -> str | None:
    tools = issue.metadata.get("implicated_tools", [])
    if isinstance(tools, list) and tools:
        return str(tools[0])
    return None


def _first_source_trace(issue: Issue, traces: list[Trace]) -> Trace | None:
    trace_by_id = {trace.trace_id: trace for trace in traces}
    for trace_id in issue.evidence_trace_ids:
        trace = trace_by_id.get(trace_id)
        if trace is not None:
            return trace
    return None
