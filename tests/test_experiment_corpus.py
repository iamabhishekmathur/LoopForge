from __future__ import annotations

from pathlib import Path

import pytest

from loopforge.experiments.corpus import (
    CaseAssignment,
    assert_no_holdout_leak,
    build_corpus,
    proposer_visible_cases,
    _trace_without_identifiers,
)
from loopforge.experiments.models import ExperimentCase
from loopforge.experiments.proposer import SearchWorkspace
from loopforge.models.issue import Issue
from loopforge.models.trace import Span, Trace


class Curator:
    curator_id = "test-curator"

    def assign(self, issue: Issue, traces: list[Trace]) -> list[CaseAssignment]:
        return [
            CaseAssignment("trace-search", "search", "known failure"),
            CaseAssignment("trace-control", "control", "acceptable behavior"),
            CaseAssignment("trace-holdout", "holdout", "unseen behavior"),
        ]


def trace(trace_id: str) -> Trace:
    return Trace(
        schema_version="1",
        trace_id=trace_id,
        started_at="2026-01-01T00:00:00Z",
        inputs={"query": trace_id},
        outputs={"answer": trace_id},
        spans=[Span("span-1", "agent", "agent", "2026-01-01T00:00:00Z")],
    )


def issue() -> Issue:
    return Issue(
        issue_id="ISSUE-1",
        title="Missed user intent",
        primary_ontology_id="MODEL_HYPOTHESIS",
        ontology_version="1",
        failure_layer="agent_response",
        trace_observability="full",
        severity="medium",
        confidence=0.9,
        evidence_trace_ids=["trace-search"],
        recommended_patch_layers=["system_prompt"],
    )


def test_holdout_is_absent_from_proposer_view_and_denied_by_workspace(tmp_path: Path) -> None:
    cases = build_corpus(
        "SEARCH-1",
        issue(),
        [trace("trace-search"), trace("trace-control"), trace("trace-holdout")],
        Curator(),
        created_at="2026-01-01T00:00:00Z",
    )
    visible = proposer_visible_cases(cases)
    workspace = SearchWorkspace(
        tmp_path,
        issue().to_dict(),
        cases,
        [{"candidate_id": "C-1", "round_number": 1}],
        [
            {
                "candidate_id": "C-1",
                "objectives": {"quality": 0.9},
                "cases": [
                    {"case_id": "visible", "trace_id": "trace-search", "split": "search"},
                    {"case_id": "secret", "trace_id": "trace-holdout", "split": "holdout"},
                ],
            }
        ],
    )

    assert {item["split"] for item in visible} == {"search", "control"}
    assert "trace-holdout" not in repr(workspace.summary())
    assert "trace-holdout" not in repr(
        workspace.run_action({"action": "inspect_candidate", "candidate_id": "C-1"})
    )
    with pytest.raises(PermissionError, match="holdout"):
        workspace.run_action({"action": "inspect_trace", "trace_id": "trace-holdout"})
    with pytest.raises(ValueError, match="holdout isolation violation"):
        assert_no_holdout_leak({"trace_id": "trace-holdout"}, cases)


def test_corpus_rejects_missing_control_split() -> None:
    class BrokenCurator:
        curator_id = "broken"

        def assign(self, issue: Issue, traces: list[Trace]) -> list[CaseAssignment]:
            return [
                CaseAssignment("trace-search", "search", "failure"),
                CaseAssignment("trace-control", "holdout", "hidden"),
            ]

    with pytest.raises(ValueError, match="acceptable control"):
        build_corpus(
            "SEARCH-1",
            issue(),
            [trace("trace-search"), trace("trace-control")],
            BrokenCurator(),
            created_at="2026-01-01T00:00:00Z",
        )


def test_external_curation_payload_removes_real_trace_identifiers() -> None:
    payload = _trace_without_identifiers(trace("9cfd3972-a9bd-43af-9d55-71f9f7b44a30"))
    assert "trace_id" not in payload
    assert "source_trace_id" not in payload
    assert "session_id" not in payload
