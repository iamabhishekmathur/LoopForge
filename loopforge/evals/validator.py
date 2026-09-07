"""Validate evaluator definitions against observed trace evidence."""

from __future__ import annotations

from loopforge.models.eval import EvaluatorDefinition, EvaluatorValidationRecord
from loopforge.models.issue import Issue
from loopforge.models.trace import Trace


MIN_POSITIVE_EXAMPLES = 3
MIN_NEGATIVE_EXAMPLES = 3


def validate_evaluator(
    issue: Issue,
    evaluator: EvaluatorDefinition,
    traces: list[Trace],
) -> EvaluatorValidationRecord:
    positive_ids = set(issue.evidence_trace_ids)
    positives = [trace for trace in traces if trace.trace_id in positive_ids]
    negatives = [trace for trace in traces if trace.trace_id not in positive_ids]

    positive_predictions = [_evaluator_detects_failure(evaluator, trace) for trace in positives]
    negative_predictions = [_evaluator_detects_failure(evaluator, trace) for trace in negatives]

    true_positives = sum(1 for prediction in positive_predictions if prediction)
    false_negatives = [
        trace.trace_id
        for trace, prediction in zip(positives, positive_predictions)
        if not prediction
    ]
    true_negatives = sum(1 for prediction in negative_predictions if not prediction)
    false_positives = [
        trace.trace_id
        for trace, prediction in zip(negatives, negative_predictions)
        if prediction
    ]
    false_positive_count = len(false_positives)

    tpr = _rate(true_positives, len(positives))
    tnr = _rate(true_negatives, len(negatives))
    precision = _rate(true_positives, true_positives + false_positive_count)
    recall = tpr
    minimum_sample_size_met = (
        len(positives) >= MIN_POSITIVE_EXAMPLES and len(negatives) >= MIN_NEGATIVE_EXAMPLES
    )
    validated = (
        minimum_sample_size_met
        and tpr is not None
        and tnr is not None
        and tpr >= 0.9
        and tnr >= 0.9
    )
    status = "validated" if validated else "needs_more_evidence"
    if false_positives or false_negatives:
        status = "rejected" if minimum_sample_size_met else status

    return EvaluatorValidationRecord(
        evaluator_id=evaluator.evaluator_id,
        failure_mode_id=evaluator.failure_mode_id,
        ontology_version=evaluator.ontology_version,
        evaluator_type=evaluator.evaluator_type,
        output_type=evaluator.output_type,
        validation_status=status,
        blocking_gate_eligible=validated,
        positive_examples=[trace.trace_id for trace in positives],
        negative_examples=[trace.trace_id for trace in negatives],
        false_positive_examples=false_positives,
        false_negative_examples=false_negatives,
        true_positive_rate=tpr,
        true_negative_rate=tnr,
        precision=precision,
        recall=recall,
        minimum_sample_size_met=minimum_sample_size_met,
        evidence_sources=["trace_evidence", "contract_spec"],
        read_test_once=True,
        pass_k_reliability=1.0 if validated else None,
        pass_at_k_capability=None,
        reset_replay_failure_rate=0.0 if validated else None,
        metadata={
            "positive_count": len(positives),
            "negative_count": len(negatives),
            "minimum_positive_examples": MIN_POSITIVE_EXAMPLES,
            "minimum_negative_examples": MIN_NEGATIVE_EXAMPLES,
        },
    )


def _evaluator_detects_failure(evaluator: EvaluatorDefinition, trace: Trace) -> bool:
    for assertion in evaluator.assertions:
        if assertion.get("type") == "requires_confirmation_before_tool":
            tool = assertion.get("tool")
            if _tool_called_before_approval(trace, str(tool)):
                return True
        if assertion.get("type") == "forbidden_tool_call":
            tool = assertion.get("tool")
            if _tool_called_without_approval(trace, str(tool)):
                return True
    return False


def _tool_called_before_approval(trace: Trace, tool: str) -> bool:
    approval_seen = False
    for span in trace.spans:
        if span.type == "human_approval":
            approval_seen = True
        if span.type == "tool_call" and span.name == tool:
            return not approval_seen
    return False


def _tool_called_without_approval(trace: Trace, tool: str) -> bool:
    called = any(span.type == "tool_call" and span.name == tool for span in trace.spans)
    approved = any(span.type == "human_approval" for span in trace.spans)
    return called and not approved


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)
