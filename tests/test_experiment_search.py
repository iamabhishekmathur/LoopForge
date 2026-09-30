from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any

from loopforge.db import Store
from loopforge.experiments.corpus import CaseAssignment
from loopforge.experiments.evaluation import PairwiseDecision
from loopforge.experiments.execution import ExecutionResult
from loopforge.experiments.models import ExperimentCandidate, ExperimentCase, SearchSession
from loopforge.experiments.search import create_search_session, promote_candidate, run_search
from loopforge.gates.runner import run_gates
from loopforge.models.issue import Issue
from loopforge.models.patch import PatchBundle
from loopforge.models.trace import Span, Trace
from loopforge.replay.runner import ReplayReport


class Curator:
    curator_id = "fixture-curator"

    def assign(self, issue: Issue, traces: list[Trace]) -> list[CaseAssignment]:
        return [
            CaseAssignment("trace-search", "search", "known failure"),
            CaseAssignment("trace-control", "control", "known acceptable"),
            CaseAssignment("trace-holdout", "holdout", "unseen related case"),
        ]


class Proposer:
    proposer_id = "fixture-proposer"

    def propose(self, workspace, session: SearchSession, *, round_number: int, count: int):
        baseline = next(
            item["candidate_id"]
            for item in workspace.candidates
            if item["round_number"] == 0
        )
        original = (workspace.root / "harness" / "system.md").read_text(encoding="utf-8")
        sha = hashlib.sha256(original.encode("utf-8")).hexdigest()
        modes = [("SAFE_FIX", "narrow fix"), ("BROAD_FIX", "broad fix")]
        return [
            {
                "parent_candidate_ids": [baseline],
                "hypothesis": {
                    "statement": statement,
                    "expected_effect": "Improve the failing answer.",
                    "affected_case_classes": ["failure"],
                    "unaffected_case_classes": ["acceptable"],
                    "possible_confounds": [],
                    "disproof_condition": "No target improvement or a control regression.",
                },
                "file_updates": [
                    {
                        "path": "harness/system.md",
                        "expected_sha256": sha,
                        "content": f"{original}\n{mode}\n",
                    }
                ],
                "risk_assessment": "fixture",
                "rollback_plan": "revert",
            }
            for mode, statement in modes[:count]
        ]


class Adapter:
    adapter_id = "fixture-adapter"

    def execute(self, root: Path, candidate: ExperimentCandidate, case: ExperimentCase):
        content = " ".join(str(item.get("content")) for item in candidate.file_updates)
        mode = "safe" if "SAFE_FIX" in content else "broad" if "BROAD_FIX" in content else "baseline"
        scores = {
            "baseline": {"search": 0.2, "control": 0.9, "holdout": 0.5},
            "safe": {"search": 0.9, "control": 0.9, "holdout": 0.85},
            "broad": {"search": 0.9, "control": 0.3, "holdout": 0.8},
        }
        score = scores[mode][case.split]
        return ExecutionResult(
            candidate.candidate_id,
            case.case_id,
            "completed",
            {"score": score, "mode": mode},
            {"events": [{"type": "final", "score": score}]},
            {"cost_usd": 0.01 if mode != "baseline" else 0.005, "latency_ms": 10, "tool_calls": 1},
        )


class Evaluator:
    evaluator_id = "fixture-independent-evaluator"

    def judge(self, case, baseline, candidate, context, *, candidate_first: bool):
        candidate_score = float(candidate.output["score"])
        baseline_score = float(baseline.output["score"])
        preferred = "candidate" if candidate_score > baseline_score else "tie" if candidate_score == baseline_score else "baseline"
        return PairwiseDecision(
            preferred=preferred,
            candidate_quality=candidate_score,
            baseline_quality=baseline_score,
            candidate_issue_resolution=candidate_score,
            baseline_issue_resolution=baseline_score,
            candidate_safety=1.0,
            baseline_safety=1.0,
            confidence=0.95,
            abstain=False,
            rationale=f"candidate={candidate_score}; baseline={baseline_score}",
            violated_contracts=[],
            metadata={"candidate_first": candidate_first},
        )


def trace(trace_id: str) -> Trace:
    return Trace(
        schema_version="1",
        trace_id=trace_id,
        started_at="2026-01-01T00:00:00Z",
        inputs={"query": trace_id},
        outputs={"answer": trace_id},
        spans=[Span(f"span-{trace_id}", "agent", "agent", "2026-01-01T00:00:00Z")],
    )


def issue() -> Issue:
    return Issue(
        issue_id="ISSUE-SEARCH",
        title="Agent misses the requested answer",
        primary_ontology_id="MODEL_HYPOTHESIS",
        ontology_version="1",
        failure_layer="agent_response",
        trace_observability="full",
        severity="medium",
        confidence=0.9,
        evidence_trace_ids=["trace-search"],
        recommended_patch_layers=["system_prompt"],
        metadata={
            "implicated_artifacts": [
                {"path": "harness/system.md", "artifact_type": "system_prompt"}
            ]
        },
    )


def test_search_rejects_regression_and_promotes_only_verified_frontier(tmp_path: Path) -> None:
    (tmp_path / "harness").mkdir()
    source = tmp_path / "harness" / "system.md"
    source.write_text("Answer the user.\n", encoding="utf-8")
    traces = [trace("trace-search"), trace("trace-control"), trace("trace-holdout")]
    session = create_search_session(
        tmp_path,
        issue(),
        traces,
        Curator(),
        proposer_id=Proposer.proposer_id,
        evaluator_id=Evaluator.evaluator_id,
        max_rounds=1,
        candidates_per_round=2,
        created_at="2026-01-01T00:00:00Z",
    )

    result = run_search(tmp_path, session.session_id, Proposer(), Evaluator(), Adapter())

    assert result.session.status == "completed"
    assert result.verified_candidate_count == 1
    assert len(result.frontier_candidate_ids) == 1
    assert source.read_text(encoding="utf-8") == "Answer the user.\n"
    store = Store.for_project(tmp_path)
    try:
        candidates = store.list_experiment_candidates(session.session_id)
        broad = next(item for item in candidates if "broad fix" in item["hypothesis"]["statement"])
        assert broad["status"] == "rejected"
        visible = store.list_candidate_evaluations(
            session.session_id, candidate_id=broad["candidate_id"]
        )
        assert not any((item.get("metadata") or {}).get("staged_holdout") for item in visible)
    finally:
        store.close()

    promoted = promote_candidate(
        tmp_path, session.session_id, result.frontier_candidate_ids[0]
    )
    assert promoted.promoted_candidate_id == result.frontier_candidate_ids[0]
    assert source.read_text(encoding="utf-8") == "Answer the user.\n"
    store = Store.for_project(tmp_path)
    try:
        patch = store.get_patch_bundle(f"PATCH-{result.frontier_candidate_ids[0]}")
        assert patch is not None
        assert patch["new_eval_ids"]
        validations = store.list_validations_for_issue(issue().issue_id)
        assert any(item["blocking_gate_eligible"] for item in validations)
        replay = store.get_replay_report_for_patch(patch["patch_id"])
        assert replay is not None
        assert replay["metadata"]["actual_execution"] is True
        gate = run_gates(
            PatchBundle.from_dict(patch),
            store.get_issue(issue().issue_id) or {},
            store.list_evals_for_issue(issue().issue_id),
            store.list_validations_for_issue(issue().issue_id),
            ReplayReport(
                replay["replay_id"], replay["patch_id"], replay["status"],
                replay["passed_cases"], replay["failed_cases"], replay["cases"],
                replay["metadata"],
            ),
            store.list_refinement_operations_for_patch(patch["patch_id"]),
        )
        assert gate.status == "pass"
        assert next(
            suite for suite in gate.suites if suite["name"] == "experiment_verification"
        )["status"] == "pass"
    finally:
        store.close()


def test_search_requires_independent_proposer_and_evaluator(tmp_path: Path) -> None:
    (tmp_path / "harness").mkdir()
    (tmp_path / "harness" / "system.md").write_text("x", encoding="utf-8")
    try:
        create_search_session(
            tmp_path,
            issue(),
            [trace("trace-search"), trace("trace-control"), trace("trace-holdout")],
            Curator(),
            proposer_id="same",
            evaluator_id="same",
        )
    except ValueError as exc:
        assert "independently" in str(exc)
    else:
        raise AssertionError("same proposer and evaluator identity should be rejected")
