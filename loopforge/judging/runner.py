"""Run hypothesis judging over stored traces."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from loopforge.db import Store
from loopforge.models.harness import HarnessArtifact
from loopforge.models.hypothesis import HypothesisFinding
from loopforge.models.trace import Trace
from loopforge.judging.behavior_map import build_behavior_map
from loopforge.judging.hypothesis import judge_hypotheses
from loopforge.judging.interpreter import interpret_trace
from loopforge.judging.planner import plan_judges


@dataclass(frozen=True)
class JudgeRunResult:
    trace_count: int
    behavior_artifact_count: int
    finding_count: int
    stored_count: int


def run_hypothesis_judging(root: Path, limit: int | None = None) -> JudgeRunResult:
    store = Store.for_project(root)
    try:
        trace_payloads = store.list_traces(limit=limit)
        artifact_payloads = store.list_harness_artifacts()
        artifacts = [HarnessArtifact.from_dict(payload) for payload in artifact_payloads]
        behavior_map = build_behavior_map(artifacts)
        findings: list[HypothesisFinding] = []
        for payload in trace_payloads:
            trace = Trace.from_dict(payload)
            observed = interpret_trace(trace)
            plan = plan_judges(observed, behavior_map)
            for finding in judge_hypotheses(observed, plan, behavior_map):
                store.upsert_hypothesis_finding(finding.to_dict())
                findings.append(finding)
    finally:
        store.close()
    return JudgeRunResult(
        trace_count=len(trace_payloads),
        behavior_artifact_count=len(artifacts),
        finding_count=len(findings),
        stored_count=len(findings),
    )

