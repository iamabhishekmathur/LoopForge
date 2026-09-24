"""Persist issues and their acceptance-gated downstream artifacts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from loopforge.analysis.judge import write_diagnosis
from loopforge.db import Store
from loopforge.evals.artifacts import write_eval_artifacts
from loopforge.evals.generator import generate_eval_for_issue
from loopforge.evals.validator import validate_evaluator
from loopforge.issues.report import write_issue_report
from loopforge.issues.resolution import build_resolution_plan, write_resolution_plan
from loopforge.models.issue import Issue
from loopforge.models.trace import Trace


@dataclass(frozen=True)
class IssueMaterializationResult:
    issue_count: int
    eval_count: int
    validation_count: int
    resolution_count: int
    report_paths: list[Path]


def materialize_issues(
    root: Path,
    store: Store,
    issues: list[Issue],
    traces: list[Trace],
    *,
    source: str,
    window: str | None = None,
) -> IssueMaterializationResult:
    reports: list[Path] = []
    eval_count = 0
    validation_count = 0
    resolution_count = 0
    for issue in issues:
        issue = _attach_structured_diagnosis(root, issue)
        generated = generate_eval_for_issue(issue, traces)
        if generated is not None:
            eval_example, evaluator = generated
            validation = validate_evaluator(issue, evaluator, traces)
            eval_paths = write_eval_artifacts(root, eval_example, evaluator, validation)
            store.upsert_eval_example(eval_example.to_dict())
            store.upsert_evaluator_definition(evaluator.to_dict())
            store.upsert_evaluator_validation_record(validation.to_dict())
            eval_count += 1
            validation_count += 1
            issue = replace(
                issue,
                metadata={
                    **issue.metadata,
                    "eval_artifacts": [
                        {
                            "kind": "eval",
                            "path": eval_paths["eval"].relative_to(root).as_posix(),
                            "status": eval_example.status,
                        },
                        {
                            "kind": "evaluator",
                            "path": eval_paths["evaluator"].relative_to(root).as_posix(),
                            "status": evaluator.status,
                        },
                        {
                            "kind": "validation",
                            "path": eval_paths["validation"].relative_to(root).as_posix(),
                            "status": validation.validation_status,
                        },
                    ],
                },
            )
        store.upsert_issue(issue.to_dict())
        issue_artifacts = issue.metadata.get("implicated_artifacts", [])
        plan = build_resolution_plan(
            issue,
            artifacts=issue_artifacts if isinstance(issue_artifacts, list) else [],
            evals=store.list_evals_for_issue(issue.issue_id),
            validations=store.list_validations_for_issue(issue.issue_id),
        )
        plan_paths = write_resolution_plan(root, plan)
        store.upsert_resolution_plan(plan.to_dict())
        resolution_count += 1
        event_metadata = {"source": source}
        if window:
            event_metadata["window"] = window
        store.add_issue_event(
            {
                "schema_version": "1",
                "event_id": f"{issue.issue_id}-opened",
                "issue_id": issue.issue_id,
                "event_type": "opened",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "metadata": event_metadata,
            }
        )
        reports.append(write_issue_report(root, issue))
        reports.append(plan_paths["markdown"])
    return IssueMaterializationResult(
        issue_count=len(issues),
        eval_count=eval_count,
        validation_count=validation_count,
        resolution_count=resolution_count,
        report_paths=reports,
    )


def _attach_structured_diagnosis(root: Path, issue: Issue) -> Issue:
    diagnosis_payload = issue.metadata.get("diagnosis")
    if not isinstance(diagnosis_payload, dict):
        return issue
    if "ontology_id" not in diagnosis_payload or "trace_scores" not in diagnosis_payload:
        return issue
    from loopforge.analysis.authorization import diagnosis_from_dict

    diagnosis_path = write_diagnosis(root, diagnosis_from_dict(diagnosis_payload))
    return replace(
        issue,
        metadata={
            **issue.metadata,
            "diagnosis_artifact": diagnosis_path.relative_to(root).as_posix(),
        },
    )
