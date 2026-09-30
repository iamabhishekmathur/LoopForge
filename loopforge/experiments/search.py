"""End-to-end, resumable harness search orchestration."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from loopforge.db import Store
from loopforge.experiments.corpus import CaseCurator, build_corpus, split_counts
from loopforge.experiments.evaluation import (
    PairwiseEvaluator,
    combine_stage_evaluations,
    evaluate_candidate,
    qualify_pairwise_evaluator,
)
from loopforge.experiments.execution import ExecutionAdapter, ExecutionResult, validate_file_updates
from loopforge.experiments.models import (
    CandidateEvaluation,
    CandidateHypothesis,
    ExperimentCandidate,
    ExperimentCase,
    ObjectiveVector,
    ParetoSnapshot,
    SearchEvent,
    SearchSession,
)
from loopforge.experiments.pareto import pareto_frontier
from loopforge.experiments.proposer import (
    CandidateProposer,
    SearchWorkspace,
    materialize_candidates,
)
from loopforge.models.issue import Issue
from loopforge.models.eval import EvalExample, EvaluatorDefinition, EvaluatorValidationRecord
from loopforge.models.patch import PatchBundle
from loopforge.models.trace import Trace
from loopforge.paths import LOCAL_DIR
from loopforge.refinements.ledger import refinement_operations_for_patch, write_refinement_operations
from loopforge.replay.runner import ReplayReport, write_replay_report


@dataclass(frozen=True)
class SearchRunResult:
    session: SearchSession
    candidate_count: int
    verified_candidate_count: int
    frontier_candidate_ids: list[str]
    report_path: Path


def create_search_session(
    root: Path,
    issue: Issue,
    traces: list[Trace],
    curator: CaseCurator,
    *,
    proposer_id: str,
    evaluator_id: str,
    max_rounds: int = 3,
    candidates_per_round: int = 3,
    created_at: str | None = None,
) -> SearchSession:
    if proposer_id == evaluator_id:
        raise ValueError("candidate proposer and evaluator must be independently identified")
    now = created_at or datetime.now(UTC).isoformat()
    digest = hashlib.sha256(f"{issue.issue_id}:{now}".encode("utf-8")).hexdigest()[:12]
    session_id = f"SEARCH-{digest}"
    store = Store.for_project(root)
    try:
        if store.get_issue(issue.issue_id) is None:
            store.upsert_issue(issue.to_dict())
        baseline_state_id = _baseline_state_id(store, root)
        cases = build_corpus(session_id, issue, traces, curator, created_at=now)
        counts = split_counts(cases)
        session = SearchSession(
            session_id=session_id,
            issue_id=issue.issue_id,
            baseline_state_id=baseline_state_id,
            status="created",
            created_at=now,
            updated_at=now,
            max_rounds=max_rounds,
            candidates_per_round=candidates_per_round,
            proposer_id=proposer_id,
            evaluator_id=evaluator_id,
            search_case_ids=[case.case_id for case in cases if case.split == "search"],
            control_case_ids=[case.case_id for case in cases if case.split == "control"],
            holdout_case_ids=[case.case_id for case in cases if case.split == "holdout"],
            metadata={"curator_id": curator.curator_id, "split_counts": counts},
        )
        store.upsert_search_session(session.to_dict())
        for case in cases:
            store.upsert_experiment_case(case.to_dict())
        baseline = _baseline_candidate(session, now)
        store.upsert_experiment_candidate(baseline.to_dict())
        _record_event(store, session_id, "session_created", now, payload={"split_counts": counts})
        _write_json(root, session_id, "session.json", session.to_dict())
        _write_json(root, session_id, "cases.json", [case.to_dict() for case in cases])
        return session
    finally:
        store.close()


def run_search(
    root: Path,
    session_id: str,
    proposer: CandidateProposer,
    evaluator: PairwiseEvaluator,
    execution_adapter: ExecutionAdapter,
    *,
    judge_repetitions: int = 3,
) -> SearchRunResult:
    store = Store.for_project(root)
    try:
        session_payload = store.get_search_session(session_id)
        if session_payload is None:
            raise ValueError(f"unknown search session: {session_id}")
        session = SearchSession.from_dict(session_payload)
        if proposer.proposer_id != session.proposer_id:
            raise ValueError("configured proposer does not match the session")
        if evaluator.evaluator_id != session.evaluator_id:
            raise ValueError("configured evaluator does not match the session")
        issue = store.get_issue(session.issue_id)
        if issue is None:
            raise ValueError(f"search issue no longer exists: {session.issue_id}")
        cases = [ExperimentCase.from_dict(item) for item in store.list_experiment_cases(session_id)]
        visible_cases = [case for case in cases if case.split != "holdout"]
        holdout_cases = [case for case in cases if case.split == "holdout"]
        baseline = ExperimentCandidate.from_dict(
            next(
                item
                for item in store.list_experiment_candidates(session_id)
                if item["round_number"] == 0
            )
        )
        now = datetime.now(UTC).isoformat()
        session = replace(
            session,
            status="running",
            updated_at=now,
            metadata={**session.metadata, "judge_repetitions": judge_repetitions},
        )
        store.upsert_search_session(session.to_dict())
        _record_event(store, session_id, "search_started", now)

        baseline_results = _execute_cases(root, baseline, cases, execution_adapter)
        _write_json(
            root,
            session_id,
            f"{baseline.candidate_id}/executions.json",
            {key: value.to_dict() for key, value in baseline_results.items()},
        )
        if any(result.status != "completed" for result in baseline_results.values()):
            return _block_session(
                root, store, session, "baseline execution failed; candidate comparisons are invalid"
            )
        qualification_case = visible_cases[0]
        qualification = qualify_pairwise_evaluator(
            evaluator,
            qualification_case,
            baseline_results[qualification_case.case_id],
            _behavior_context(root, issue, baseline),
        )
        _write_json(root, session_id, "evaluator-qualification.json", qualification)
        _record_event(
            store,
            session_id,
            "evaluator_qualified" if qualification["status"] == "pass" else "evaluator_rejected",
            datetime.now(UTC).isoformat(),
            payload={"checks": qualification["checks"]},
        )
        if qualification["status"] != "pass":
            return _block_session(
                root, store, session, "independent evaluator failed identity-invariance checks"
            )
        session = replace(
            session,
            updated_at=datetime.now(UTC).isoformat(),
            metadata={**session.metadata, "evaluator_qualification": qualification},
        )
        store.upsert_search_session(session.to_dict())

        snapshots = store.list_pareto_snapshots(session_id)
        completed_rounds = max((int(item["round_number"]) for item in snapshots), default=0)
        for item in store.list_experiment_candidates(session_id):
            if int(item["round_number"]) <= completed_rounds or int(item["round_number"]) == 0:
                continue
            interrupted = replace(
                ExperimentCandidate.from_dict(item),
                status="abandoned_after_interrupted_round",
            )
            store.upsert_experiment_candidate(interrupted.to_dict())
        for round_number in range(completed_rounds + 1, session.max_rounds + 1):
            workspace = SearchWorkspace(
                root=root,
                issue=issue,
                cases=cases,
                candidates=store.list_all_experiment_candidates(),
                evaluations=store.list_all_candidate_evaluations(),
            )
            proposals = proposer.propose(
                workspace,
                session,
                round_number=round_number,
                count=session.candidates_per_round,
            )
            candidates = materialize_candidates(
                root,
                session,
                proposals,
                round_number=round_number,
                proposer_id=proposer.proposer_id,
            )
            known_ids = {
                item["candidate_id"] for item in store.list_experiment_candidates(session_id)
            }
            for candidate in candidates:
                candidate = _validate_candidate(root, candidate, known_ids)
                store.upsert_experiment_candidate(candidate.to_dict())
                _write_candidate(root, candidate)
                _record_event(
                    store,
                    session_id,
                    "candidate_proposed",
                    candidate.created_at,
                    candidate_id=candidate.candidate_id,
                    payload={"status": candidate.status},
                )
                if candidate.status == "invalid":
                    store.upsert_candidate_evaluation(
                        _invalid_evaluation(session, candidate, evaluator.evaluator_id).to_dict()
                    )
                    continue
                candidate_results = _execute_cases(
                    root, candidate, visible_cases, execution_adapter
                )
                visible_evaluation = evaluate_candidate(
                    session_id,
                    candidate.candidate_id,
                    visible_cases,
                    baseline_results,
                    candidate_results,
                    evaluator,
                    _behavior_context(root, issue, candidate),
                    repetitions=judge_repetitions,
                )
                store.upsert_candidate_evaluation(visible_evaluation.to_dict())
                _write_json(
                    root,
                    session_id,
                    f"{candidate.candidate_id}/visible-evaluation.json",
                    visible_evaluation.to_dict(),
                )
                if not _visible_stage_passed(visible_evaluation):
                    rejected = replace(candidate, status="rejected")
                    store.upsert_experiment_candidate(rejected.to_dict())
                    _record_event(
                        store,
                        session_id,
                        "candidate_rejected_before_holdout",
                        datetime.now(UTC).isoformat(),
                        candidate_id=candidate.candidate_id,
                        payload={"evaluation_id": visible_evaluation.evaluation_id},
                    )
                    continue

                holdout_results = _execute_cases(
                    root, candidate, holdout_cases, execution_adapter
                )
                candidate_results.update(holdout_results)
                holdout_evaluation = evaluate_candidate(
                    session_id,
                    candidate.candidate_id,
                    holdout_cases,
                    baseline_results,
                    holdout_results,
                    evaluator,
                    _behavior_context(root, issue, candidate),
                    repetitions=judge_repetitions,
                )
                combined = combine_stage_evaluations(visible_evaluation, holdout_evaluation)
                store.upsert_candidate_evaluation(holdout_evaluation.to_dict())
                store.upsert_candidate_evaluation(combined.to_dict())
                _write_json(
                    root,
                    session_id,
                    f"{candidate.candidate_id}/executions.json",
                    {key: value.to_dict() for key, value in candidate_results.items()},
                )
                _write_json(
                    root,
                    session_id,
                    f"{candidate.candidate_id}/evaluation.json",
                    combined.to_dict(),
                )
                verified = replace(
                    candidate,
                    status="verified" if combined.status == "pass" else "rejected",
                )
                store.upsert_experiment_candidate(verified.to_dict())
                _record_event(
                    store,
                    session_id,
                    "candidate_evaluated",
                    datetime.now(UTC).isoformat(),
                    candidate_id=candidate.candidate_id,
                    payload={
                        "evaluation_id": combined.evaluation_id,
                        "status": combined.status,
                    },
                )
                known_ids.add(candidate.candidate_id)

            _snapshot_frontier(root, store, session, round_number)

        finished = datetime.now(UTC).isoformat()
        session = replace(session, status="completed", updated_at=finished)
        store.upsert_search_session(session.to_dict())
        _record_event(store, session_id, "search_completed", finished)
        snapshots = store.list_pareto_snapshots(session_id)
        frontier = list(snapshots[-1].get("candidate_ids") or []) if snapshots else []
        report_path = _write_search_report(root, store, session, frontier)
        combined_evaluations = _combined_evaluations(store, session_id)
        return SearchRunResult(
            session=session,
            candidate_count=len(store.list_experiment_candidates(session_id)) - 1,
            verified_candidate_count=sum(
                evaluation.status == "pass" for evaluation in combined_evaluations
            ),
            frontier_candidate_ids=frontier,
            report_path=report_path,
        )
    except Exception:
        payload = store.get_search_session(session_id)
        if payload is not None:
            failed = replace(
                SearchSession.from_dict(payload),
                status="blocked",
                updated_at=datetime.now(UTC).isoformat(),
            )
            store.upsert_search_session(failed.to_dict())
        raise
    finally:
        store.close()


def promote_candidate(root: Path, session_id: str, candidate_id: str) -> SearchSession:
    store = Store.for_project(root)
    try:
        payload = store.get_search_session(session_id)
        candidate_payload = store.get_experiment_candidate(candidate_id)
        if payload is None or candidate_payload is None:
            raise ValueError("unknown search session or candidate")
        snapshots = store.list_pareto_snapshots(session_id)
        frontier = set(snapshots[-1].get("candidate_ids") or []) if snapshots else set()
        if candidate_id not in frontier:
            raise ValueError("only a verified Pareto-frontier candidate can be promoted")
        session = SearchSession.from_dict(payload)
        now = datetime.now(UTC).isoformat()
        session = replace(session, promoted_candidate_id=candidate_id, updated_at=now)
        candidate = ExperimentCandidate.from_dict(candidate_payload)
        candidate = replace(candidate, status="promoted")
        issue_payload = store.get_issue(session.issue_id)
        if issue_payload is None:
            raise ValueError(f"search issue no longer exists: {session.issue_id}")
        evaluations = _combined_evaluations(store, session_id)
        evaluation = next(
            (item for item in reversed(evaluations) if item.candidate_id == candidate_id),
            None,
        )
        if evaluation is None:
            raise ValueError("promoted candidate is missing its combined verification record")
        search_eval_id = _persist_search_evaluator(
            store, session, candidate, evaluation, issue_payload
        )
        patch_payload = dict(candidate.patch_bundle)
        patch_payload["new_eval_ids"] = [
            item["eval_id"] for item in store.list_evals_for_issue(session.issue_id)
        ]
        patch_payload["status"] = "drafted"
        patch_payload["target_artifacts"] = _ground_target_artifacts(
            patch_payload.get("target_artifacts") or [], issue_payload
        )
        patch_payload["metadata"] = {
            **dict(patch_payload.get("metadata") or {}),
            "search_session_id": session_id,
            "candidate_id": candidate_id,
            "search_evaluation_id": evaluation.evaluation_id,
            "search_eval_id": search_eval_id,
            "actual_execution_verified": True,
            "holdout_isolated": evaluation.verification.get("holdout_isolated") is True,
            "target_improvement_delta": evaluation.verification.get(
                "target_improvement_delta", 0.0
            ),
            "search_objectives": evaluation.objectives.to_dict(),
            "expected_outcome": candidate.hypothesis.expected_effect,
            "validation_plan": (
                "Retain the verified search, control, and hidden-holdout results; run normal "
                "review gates, then shadow and canary confirmation."
            ),
            "patch_layer": _promoted_patch_layer(issue_payload),
            "refinement_scope": "workflow",
            "reviewer_boundary": "agent_architecture_review",
            "requires_human_approval": True,
        }
        patch = PatchBundle.from_dict(patch_payload)
        issue = Issue.from_dict(issue_payload)
        operations = refinement_operations_for_patch(issue, patch)
        replay = _experiment_replay_report(patch, evaluation)
        store.upsert_search_session(session.to_dict())
        store.upsert_experiment_candidate(candidate.to_dict())
        store.upsert_patch_bundle(patch.to_dict())
        for operation in operations:
            store.upsert_refinement_operation(operation.to_dict())
        store.upsert_replay_report(replay.to_dict())
        write_refinement_operations(root, operations)
        write_replay_report(root, replay)
        _record_event(
            store,
            session_id,
            "candidate_promoted_for_human_review",
            now,
            candidate_id=candidate_id,
        )
        return session
    finally:
        store.close()


def _execute_cases(
    root: Path,
    candidate: ExperimentCandidate,
    cases: list[ExperimentCase],
    adapter: ExecutionAdapter,
) -> dict[str, ExecutionResult]:
    return {case.case_id: adapter.execute(root, candidate, case) for case in cases}


def _validate_candidate(
    root: Path,
    candidate: ExperimentCandidate,
    known_ids: set[str],
) -> ExperimentCandidate:
    errors = validate_file_updates(root, candidate.file_updates)
    unknown_parents = sorted(set(candidate.parent_candidate_ids) - known_ids)
    if unknown_parents:
        errors.append(f"unknown parent candidates: {', '.join(unknown_parents)}")
    if len(candidate.file_updates) > 1 and not candidate.hypothesis.possible_confounds:
        errors.append("multi-artifact mutation must declare possible confounds")
    return replace(
        candidate,
        status="invalid" if errors else "validated",
        metadata={**candidate.metadata, "interface_validation_errors": errors},
    )


def _visible_stage_passed(evaluation: CandidateEvaluation) -> bool:
    return (
        evaluation.status == "pass"
        and evaluation.objectives.safety >= 0.99
        and evaluation.objectives.regression_free >= 0.95
        and evaluation.objectives.judge_confidence >= 0.70
        and float(evaluation.verification.get("target_improvement_delta", 0.0)) >= 0.05
    )


def _snapshot_frontier(
    root: Path,
    store: Store,
    session: SearchSession,
    round_number: int,
) -> ParetoSnapshot:
    evaluations = _combined_evaluations(store, session.session_id)
    result = pareto_frontier(evaluations)
    now = datetime.now(UTC).isoformat()
    snapshot = ParetoSnapshot(
        snapshot_id=f"FRONTIER-{session.session_id}-{round_number:03d}",
        session_id=session.session_id,
        round_number=round_number,
        candidate_ids=result.candidate_ids,
        dominated_candidate_ids=result.dominated_candidate_ids,
        created_at=now,
        metadata={"ineligible_candidate_ids": result.ineligible_candidate_ids},
    )
    store.upsert_pareto_snapshot(snapshot.to_dict())
    _write_json(root, session.session_id, f"frontier-{round_number:03d}.json", snapshot.to_dict())
    _record_event(
        store,
        session.session_id,
        "frontier_updated",
        now,
        payload={"candidate_ids": result.candidate_ids},
    )
    return snapshot


def _combined_evaluations(store: Store, session_id: str) -> list[CandidateEvaluation]:
    return [
        CandidateEvaluation.from_dict(item)
        for item in store.list_candidate_evaluations(session_id)
        if (item.get("metadata") or {}).get("staged_holdout") is True
    ]


def _behavior_context(
    root: Path,
    issue: dict[str, Any],
    candidate: ExperimentCandidate,
) -> dict[str, Any]:
    paths = {
        str(item.get("path"))
        for item in (issue.get("metadata") or {}).get("implicated_artifacts", [])
        if isinstance(item, dict) and item.get("path")
    }
    paths.update(str(item.get("path")) for item in candidate.file_updates if item.get("path"))
    evidence = []
    for relative in sorted(paths):
        path = (root / relative).resolve()
        if path.is_relative_to(root.resolve()) and path.is_file() and not path.is_symlink():
            evidence.append(
                {
                    "path": relative,
                    "content": path.read_text(encoding="utf-8")[:16000],
                }
            )
    return {
        "issue": issue,
        "candidate_hypothesis": candidate.hypothesis.to_dict(),
        "codebase_contracts": evidence,
    }


def _baseline_candidate(session: SearchSession, created_at: str) -> ExperimentCandidate:
    return ExperimentCandidate(
        candidate_id=f"BASELINE-{session.session_id}",
        session_id=session.session_id,
        round_number=0,
        parent_candidate_ids=[],
        hypothesis=CandidateHypothesis(
            statement="The current production harness is the comparison baseline.",
            expected_effect="Preserve observed behavior without mutation.",
            affected_case_classes=[],
            unaffected_case_classes=["all"],
            possible_confounds=[],
            disproof_condition="Not applicable to the baseline.",
        ),
        file_updates=[],
        patch_bundle={},
        status="baseline",
        created_at=created_at,
        proposer_id="loopforge-baseline",
    )


def _invalid_evaluation(
    session: SearchSession,
    candidate: ExperimentCandidate,
    evaluator_id: str,
) -> CandidateEvaluation:
    return CandidateEvaluation(
        evaluation_id=f"EVALUATION-{candidate.candidate_id}-INVALID",
        session_id=session.session_id,
        candidate_id=candidate.candidate_id,
        split="combined",
        status="fail",
        created_at=datetime.now(UTC).isoformat(),
        evaluator_id=evaluator_id,
        cases=[],
        objectives=ObjectiveVector(0, 0, 0, 0, 0, 0, 0, 0),
        verification={
            "verified": False,
            "holdout_isolated": True,
            "interface_validation_errors": candidate.metadata.get(
                "interface_validation_errors", []
            ),
        },
    )


def _baseline_state_id(store: Store, root: Path) -> str:
    states = store.list_harness_states()
    if states:
        return str(states[0]["state_id"])
    digest = hashlib.sha256()
    for artifact in store.list_harness_artifacts():
        path = root / str(artifact.get("path") or "")
        if path.is_file():
            digest.update(path.read_bytes())
    return f"state-current-{digest.hexdigest()[:16]}"


def _ground_target_artifacts(
    targets: list[dict[str, Any]],
    issue: dict[str, Any],
) -> list[dict[str, Any]]:
    implicated = {
        str(item.get("path")): item
        for item in (issue.get("metadata") or {}).get("implicated_artifacts", [])
        if isinstance(item, dict) and item.get("path")
    }
    grounded = []
    for target in targets:
        source = implicated.get(str(target.get("path")), {})
        grounded.append(
            {
                **target,
                "artifact_id": source.get("artifact_id")
                or target.get("artifact_id")
                or f"artifact:{target.get('path')}",
                "artifact_type": source.get("artifact_type")
                or target.get("artifact_type")
                or "harness_component",
                "confidence": float(source.get("confidence") or target.get("confidence") or 1.0),
            }
        )
    return grounded


def _promoted_patch_layer(issue: dict[str, Any]) -> str:
    layers = list(issue.get("recommended_patch_layers") or [])
    return str(layers[0]) if layers else str(issue.get("failure_layer") or "harness_component")


def _experiment_replay_report(
    patch: PatchBundle,
    evaluation: CandidateEvaluation,
) -> ReplayReport:
    cases = [
        {
            "eval_id": case.get("case_id"),
            "status": "pass" if case.get("status") == "pass" else "fail",
            "source_trace_ids": [case.get("trace_id")],
            "reason": case.get("rationale") or case.get("reason") or "experiment evaluation",
            "split": case.get("split"),
            "agreement": case.get("agreement"),
            "confidence": case.get("confidence"),
        }
        for case in evaluation.cases
    ]
    passed = sum(case["status"] == "pass" for case in cases)
    return ReplayReport(
        replay_id=f"REPLAY-{patch.patch_id}",
        patch_id=patch.patch_id,
        status="pass" if cases and passed == len(cases) else "fail",
        passed_cases=passed,
        failed_cases=len(cases) - passed,
        cases=cases,
        metadata={
            "engine": "experiment_execution_v1",
            "actual_execution": True,
            "evaluation_id": evaluation.evaluation_id,
            "holdout_isolated": evaluation.verification.get("holdout_isolated") is True,
        },
    )


def _persist_search_evaluator(
    store: Store,
    session: SearchSession,
    candidate: ExperimentCandidate,
    evaluation: CandidateEvaluation,
    issue: dict[str, Any],
) -> str:
    suffix = candidate.candidate_id.removeprefix("CANDIDATE-")
    eval_id = f"EVAL-SEARCH-{suffix}"
    evaluator_id = f"EVALUATOR-SEARCH-{suffix}"
    cases = store.list_experiment_cases(session.session_id)
    trace_by_case = {str(item["case_id"]): str(item["trace_id"]) for item in cases}
    search_cases = [case for case in evaluation.cases if case.get("split") == "search"]
    control_cases = [case for case in evaluation.cases if case.get("split") == "control"]
    agreements = [
        float(case.get("agreement") or 0.0)
        for case in evaluation.cases
        if case.get("status") == "pass"
    ]
    assertion = {
        "type": "verified_harness_search",
        "search_session_id": session.session_id,
        "candidate_id": candidate.candidate_id,
        "minimum_target_improvement_delta": 0.05,
        "minimum_control_regression_free": 0.95,
        "minimum_safety": 0.99,
        "requires_hidden_holdout": True,
        "abstain_when_insufficient": True,
    }
    eval_example = EvalExample(
        eval_id=eval_id,
        issue_id=session.issue_id,
        source_trace_ids=sorted(set(trace_by_case.values())),
        primary_ontology_id=str(issue.get("primary_ontology_id") or "MODEL_HYPOTHESIS"),
        ontology_version=str(issue.get("ontology_version") or "1"),
        input={
            "search_session_id": session.session_id,
            "candidate_id": candidate.candidate_id,
        },
        expected_behavior={"summary": candidate.hypothesis.expected_effect},
        assertions=[assertion],
        status="validated",
        metadata={
            "generated_from_verified_search": True,
            "evaluation_id": evaluation.evaluation_id,
        },
    )
    definition = EvaluatorDefinition(
        evaluator_id=evaluator_id,
        eval_id=eval_id,
        issue_id=session.issue_id,
        failure_mode_id=str(issue.get("primary_ontology_id") or "MODEL_HYPOTHESIS"),
        ontology_version=str(issue.get("ontology_version") or "1"),
        evaluator_type="repeated_blinded_pairwise_judge",
        output_type="probability_with_abstention",
        assertions=[assertion],
        status="validated",
        metadata={
            "search_session_id": session.session_id,
            "proposer_id": session.proposer_id,
            "evaluator_id": session.evaluator_id,
        },
    )
    qualification = session.metadata.get("evaluator_qualification") or {}
    eligible = (
        qualification.get("blocking_gate_eligible") is True
        and evaluation.verification.get("verified") is True
        and evaluation.verification.get("holdout_isolated") is True
        and len(evaluation.cases) >= 3
    )
    validation = EvaluatorValidationRecord(
        evaluator_id=evaluator_id,
        failure_mode_id=definition.failure_mode_id,
        ontology_version=definition.ontology_version,
        evaluator_type=definition.evaluator_type,
        output_type=definition.output_type,
        validation_status="passed" if eligible else "failed",
        blocking_gate_eligible=eligible,
        positive_examples=[str(case.get("case_id")) for case in search_cases],
        negative_examples=[str(case.get("case_id")) for case in control_cases],
        minimum_sample_size_met=len(evaluation.cases) >= 3,
        evidence_sources=[
            evaluation.evaluation_id,
            f"{session.session_id}/evaluator-qualification.json",
        ],
        pass_k_reliability=min(agreements) if agreements else 0.0,
        metadata={
            "identity_invariance": qualification.get("checks") or {},
            "holdout_case_count": sum(
                case.get("split") == "holdout" for case in evaluation.cases
            ),
            "judge_repetitions": session.metadata.get("judge_repetitions"),
        },
    )
    store.upsert_eval_example(eval_example.to_dict())
    store.upsert_evaluator_definition(definition.to_dict())
    store.upsert_evaluator_validation_record(validation.to_dict())
    return eval_id


def _record_event(
    store: Store,
    session_id: str,
    event_type: str,
    created_at: str,
    *,
    candidate_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    value = payload or {}
    digest = hashlib.sha256(
        json.dumps(
            [session_id, event_type, candidate_id, created_at, value], sort_keys=True
        ).encode("utf-8")
    ).hexdigest()[:16]
    store.add_search_event(
        SearchEvent(
            event_id=f"EVENT-{digest}",
            session_id=session_id,
            event_type=event_type,
            created_at=created_at,
            candidate_id=candidate_id,
            payload=value,
        ).to_dict()
    )


def _write_candidate(root: Path, candidate: ExperimentCandidate) -> None:
    _write_json(
        root,
        candidate.session_id,
        f"{candidate.candidate_id}/candidate.json",
        candidate.to_dict(),
    )
    directory = root / LOCAL_DIR / "experiments" / candidate.session_id / candidate.candidate_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "patch.diff").write_text(
        str(candidate.patch_bundle.get("diff") or ""), encoding="utf-8"
    )


def _write_json(
    root: Path,
    session_id: str,
    relative: str,
    payload: Any,
) -> Path:
    path = root / LOCAL_DIR / "experiments" / session_id / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _write_search_report(
    root: Path,
    store: Store,
    session: SearchSession,
    frontier: list[str],
) -> Path:
    report = {
        "schema_version": "1",
        "session": session.to_dict(),
        "frontier_candidate_ids": frontier,
        "candidates": store.list_experiment_candidates(session.session_id),
        "evaluations": store.list_candidate_evaluations(session.session_id),
        "frontier_history": store.list_pareto_snapshots(session.session_id),
        "events": store.list_search_events(session.session_id),
    }
    return _write_json(root, session.session_id, "report.json", report)


def _block_session(
    root: Path,
    store: Store,
    session: SearchSession,
    reason: str,
) -> SearchRunResult:
    now = datetime.now(UTC).isoformat()
    blocked = replace(
        session,
        status="blocked",
        updated_at=now,
        metadata={**session.metadata, "blocked_reason": reason},
    )
    store.upsert_search_session(blocked.to_dict())
    _record_event(store, session.session_id, "search_blocked", now, payload={"reason": reason})
    path = _write_search_report(root, store, blocked, [])
    return SearchRunResult(blocked, 0, 0, [], path)
