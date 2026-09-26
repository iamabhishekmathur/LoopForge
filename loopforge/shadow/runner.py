"""Reusable shadow-run pipeline for manual and scheduled monitoring."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from loopforge.adapters.registry import read_traces
from loopforge.adapters.sync import trace_window_start
from loopforge.config import configured_issue_judge
from loopforge.db import Store
from loopforge.discovery.manifest import build_runtime_manifest, write_runtime_manifest
from loopforge.discovery.scanner import discover_harness_artifacts, write_harness_index
from loopforge.issues.materialize import materialize_issues
from loopforge.issues.miner import mine_issues
from loopforge.state.graph import build_harness_state_snapshot, write_harness_state_snapshot
from loopforge.trajectories.builder import build_trajectory
from loopforge.traces.selection import select_judge_cases


@dataclass(frozen=True)
class ShadowRunResult:
    window: str
    trace_path: str
    provider_trace_count: int
    trace_count: int
    auxiliary_trace_count: int
    excluded_trace_count: int
    trajectory_count: int
    artifact_count: int
    issue_count: int
    eval_count: int
    validation_count: int
    resolution_count: int
    report_paths: list[Path]


def run_shadow_pipeline(
    root: Path,
    window: str,
    trace_path_override: str | None = None,
) -> ShadowRunResult:
    trace_path, traces = read_traces(
        root,
        trace_path_override,
        since_override=trace_window_start(window),
    )
    provider_trace_count = len(traces)
    selection = select_judge_cases(traces)
    traces = selection.cases

    store = Store.for_project(root)
    try:
        artifacts = discover_harness_artifacts(root)
        write_harness_index(root, artifacts)
        manifest = build_runtime_manifest(root, artifacts)
        write_runtime_manifest(root, manifest)
        state = build_harness_state_snapshot(artifacts, manifest)
        write_harness_state_snapshot(root, state)
        for artifact in artifacts:
            store.upsert_harness_artifact(artifact.to_dict())
        store.upsert_runtime_manifest(manifest.to_dict())
        store.upsert_harness_state(state.to_dict())

        trajectories = []
        for trace in traces:
            trace_dict = trace.to_dict()
            trajectory = build_trajectory(trace)
            trajectories.append(trajectory)
            store.upsert_trace(trace_dict)
            store.upsert_trajectory(trajectory.to_dict())

        issues = mine_issues(traces, trajectories, artifacts, judge=configured_issue_judge(root))
        materialized = materialize_issues(
            root,
            store,
            issues,
            traces,
            source="shadow",
            window=window,
        )
    finally:
        store.close()

    return ShadowRunResult(
        window=window,
        trace_path=trace_path,
        provider_trace_count=provider_trace_count,
        trace_count=len(traces),
        auxiliary_trace_count=len(selection.auxiliary_trace_ids),
        excluded_trace_count=len(selection.excluded_trace_ids),
        trajectory_count=len(trajectories),
        artifact_count=len(artifacts),
        issue_count=len(issues),
        eval_count=materialized.eval_count,
        validation_count=materialized.validation_count,
        resolution_count=materialized.resolution_count,
        report_paths=materialized.report_paths,
    )
