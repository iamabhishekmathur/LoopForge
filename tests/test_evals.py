from __future__ import annotations

from pathlib import Path

from loopforge.adapters.jsonl import JsonlTraceAdapter
from loopforge.evals.generator import generate_eval_for_issue
from loopforge.evals.validator import validate_evaluator
from loopforge.issues.miner import mine_issues
from loopforge.trajectories.builder import build_trajectory


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "support-agent"


def test_generate_eval_for_authorization_issue() -> None:
    traces = JsonlTraceAdapter("../traces/support-agent-cancellation.jsonl").read(FIXTURE_ROOT)
    trajectories = [build_trajectory(trace) for trace in traces]
    issue = mine_issues(traces, trajectories)[0]

    generated = generate_eval_for_issue(issue, traces)

    assert generated is not None
    eval_example, evaluator = generated
    assert eval_example.eval_id == "EVAL-0001"
    assert eval_example.issue_id == "ISSUE-0001"
    assert eval_example.primary_ontology_id == "ACTION_AUTHORIZATION_ERROR"
    assert {"type": "forbidden_tool_call", "tool": "cancel_subscription"} in eval_example.assertions
    assert {
        "type": "requires_confirmation_before_tool",
        "tool": "cancel_subscription",
    } in eval_example.assertions
    assert evaluator.evaluator_type == "contractual_check"


def test_validate_evaluator_against_fixture_traces() -> None:
    traces = JsonlTraceAdapter("../traces/support-agent-cancellation.jsonl").read(FIXTURE_ROOT)
    trajectories = [build_trajectory(trace) for trace in traces]
    issue = mine_issues(traces, trajectories)[0]
    generated = generate_eval_for_issue(issue, traces)
    assert generated is not None
    _, evaluator = generated

    validation = validate_evaluator(issue, evaluator, traces)

    assert validation.validation_status == "validated"
    assert validation.blocking_gate_eligible is True
    assert validation.true_positive_rate == 1.0
    assert validation.true_negative_rate == 1.0
    assert validation.false_positive_examples == []
    assert validation.false_negative_examples == []
