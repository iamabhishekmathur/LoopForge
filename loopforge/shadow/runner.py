"""Reusable shadow-run pipeline for manual and scheduled monitoring."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from loopforge.adapters.registry import read_traces
from loopforge.analysis.judge import write_diagnosis
from loopforge.db import Store
from loopforge.discovery.manifest import build_runtime_manifest, write_runtime_manifest
from loopforge.discovery.scanner import discover_harness_artifacts, write_harness_index
from loopforge.evals.artifacts import write_eval_artifacts
from loopforge.evals.generator import generate_eval_for_issue
from loopforge.evals.validator import validate_evaluator
from loopforge.issues.miner import mine_issues
from loopforge.issues.report import write_issue_report
from loopforge.trajectories.builder import build_trajectory


@dataclass(frozen=True)
class ShadowRunResult:
    window: str
    trace_path: str
    trace_count: int
    trajectory_count: int
    artifact_count: int
    issue_count: int
    eval_count: int
    validation_count: int
    report_paths: list[Path]


def run_shadow_pipeline(
    root: Path,
    window: str,
    trace_path_override: str | None = None,
) -> ShadowRunResult:
    trace_path, traces = read_traces(root, trace_path_override)

    store = Store.for_project(root)
    try:
        artifacts = discover_harness_artifacts(root)
        write_harness_index(root, artifacts)
        manifest = build_runtime_manifest(root, artifacts)
        write_runtime_manifest(root, manifest)
        for artifact in artifacts:
            store.upsert_harness_artifact(artifact.to_dict())
        store.upsert_runtime_manifest(manifest.to_dict())

        trajectories = []
        for trace in traces:
            trace_dict = trace.to_dict()
            trajectory = build_trajectory(trace)
            trajectories.append(trajectory)
            store.upsert_trace(trace_dict)
            store.upsert_trajectory(trajectory.to_dict())

        issues = mine_issues(traces, trajectories, artifacts)
        reports = []
        eval_count = 0
        validation_count = 0
        for issue in issues:
            diagnosis_payload = issue.metadata.get("diagnosis")
            if isinstance(diagnosis_payload, dict):
                from loopforge.analysis.authorization import diagnosis_from_dict

                diagnosis_path = write_diagnosis(root, diagnosis_from_dict(diagnosis_payload))
                issue = replace(
                    issue,
                    metadata={
                        **issue.metadata,
                        "diagnosis_artifact": diagnosis_path.relative_to(root).as_posix(),
                    },
                )
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
            issue_dict = issue.to_dict()
            store.upsert_issue(issue_dict)
            store.add_issue_event(
                {
                    "schema_version": "1",
                    "event_id": f"{issue.issue_id}-opened",
                    "issue_id": issue.issue_id,
                    "event_type": "opened",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "metadata": {"source": "shadow", "window": window},
                }
            )
            reports.append(write_issue_report(root, issue))
    finally:
        store.close()

    return ShadowRunResult(
        window=window,
        trace_path=trace_path,
        trace_count=len(traces),
        trajectory_count=len(trajectories),
        artifact_count=len(artifacts),
        issue_count=len(issues),
        eval_count=eval_count,
        validation_count=validation_count,
        report_paths=reports,
    )
