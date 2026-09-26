"""Run hypothesis judging over stored traces."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from loopforge.config import configured_hypothesis_judge
from loopforge.db import Store
from loopforge.evidence.archive import archive_trace
from loopforge.evidence.reducer import receipts_for_trace
from loopforge.judging.model_judge import HypothesisJudge
from loopforge.models.harness import HarnessArtifact
from loopforge.models.hypothesis import HypothesisFinding
from loopforge.models.trace import Trace
from loopforge.judging.behavior_map import build_behavior_map
from loopforge.judging.hypothesis import judge_hypotheses
from loopforge.judging.interpreter import interpret_trace
from loopforge.judging.planner import plan_judges
from loopforge.judging.promotion import promote_findings
from loopforge.issues.materialize import materialize_issues
from loopforge.traces.selection import select_judge_cases
from loopforge.traces.quality import is_analysis_eligible_trace


@dataclass(frozen=True)
class JudgeRunResult:
    input_trace_count: int
    trace_count: int
    auxiliary_trace_count: int
    excluded_trace_count: int
    behavior_artifact_count: int
    finding_count: int
    stored_count: int
    promoted_issue_count: int = 0
    eval_count: int = 0
    validation_count: int = 0
    resolution_count: int = 0


def run_hypothesis_judging(
    root: Path,
    limit: int | None = None,
    judge: HypothesisJudge | None = None,
) -> JudgeRunResult:
    store = Store.for_project(root)
    try:
        all_trace_payloads = store.list_traces()
        ineligible_trace_ids = [
            str(payload["trace_id"])
            for payload in all_trace_payloads
            if not is_analysis_eligible_trace(payload)
        ]
        store.delete_hypothesis_findings_for_traces(ineligible_trace_ids)
        trace_payloads = [
            payload for payload in all_trace_payloads if is_analysis_eligible_trace(payload)
        ]
        artifact_payloads = store.list_harness_artifacts()
        artifacts = [HarnessArtifact.from_dict(payload) for payload in artifact_payloads]
        behavior_map = build_behavior_map(artifacts)
        selected_judge = judge or configured_hypothesis_judge(root)
        selection = select_judge_cases([Trace.from_dict(payload) for payload in trace_payloads])
        traces = selection.cases[:limit] if limit is not None else selection.cases
        store.delete_hypothesis_findings_for_traces(
            selection.auxiliary_trace_ids + selection.excluded_trace_ids
        )
        for trace in traces:
            store.upsert_trace(trace.to_dict())
        store.delete_hypothesis_findings_for_traces([trace.trace_id for trace in traces])
        findings: list[HypothesisFinding] = []
        for trace in traces:
            archive_trace(root, trace.to_dict())
            observed = interpret_trace(trace)
            plan = plan_judges(observed, behavior_map)
            local_findings = judge_hypotheses(observed, plan, behavior_map)
            evidence_receipts = [
                receipt.to_dict()
                for receipt in receipts_for_trace(root, trace.trace_id)
                if receipt.verification_status == "verified"
            ]
            for finding in selected_judge.judge(
                observed,
                plan,
                behavior_map,
                local_findings,
                evidence_receipts=evidence_receipts,
            ):
                store.upsert_hypothesis_finding(finding.to_dict())
                findings.append(finding)
        promoted_issues = promote_findings(findings)
        materialized = materialize_issues(
            root,
            store,
            promoted_issues,
            traces,
            source="hypothesis_judge",
        )
    finally:
        store.close()
    return JudgeRunResult(
        input_trace_count=len(trace_payloads),
        trace_count=len(traces),
        auxiliary_trace_count=len(selection.auxiliary_trace_ids),
        excluded_trace_count=len(selection.excluded_trace_ids),
        behavior_artifact_count=len(artifacts),
        finding_count=len(findings),
        stored_count=len(findings),
        promoted_issue_count=materialized.issue_count,
        eval_count=materialized.eval_count,
        validation_count=materialized.validation_count,
        resolution_count=materialized.resolution_count,
    )
