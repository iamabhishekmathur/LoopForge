"""Initial issue screener for observable trace failures."""

from __future__ import annotations

from loopforge.analysis.authorization import diagnose_action_authorization
from loopforge.models.issue import Issue
from loopforge.models.harness import HarnessArtifact
from loopforge.models.trace import Trace
from loopforge.models.trajectory import TraceTrajectory


def mine_issues(
    traces: list[Trace],
    trajectories: list[TraceTrajectory],
    artifacts: list[HarnessArtifact] | None = None,
) -> list[Issue]:
    """Mine issue candidates from confidence-bearing trajectory diagnoses."""
    diagnosis = diagnose_action_authorization(traces, trajectories)
    if diagnosis is None:
        return []

    artifact_links = _artifact_links(diagnosis.implicated_tools, artifacts or [])
    tool_summary = (
        ", ".join(diagnosis.implicated_tools)
        if diagnosis.implicated_tools
        else "side-effecting tool"
    )

    issue = Issue(
        issue_id="ISSUE-0001",
        title=f"Side-effecting tool call without approval: {tool_summary}",
        primary_ontology_id=diagnosis.ontology_id,
        ontology_version="1",
        failure_layer="governance",
        trace_observability=diagnosis.trace_observability,
        severity=diagnosis.severity,
        confidence=diagnosis.confidence,
        evidence_trace_ids=diagnosis.evidence_trace_ids,
        recommended_patch_layers=diagnosis.recommended_patch_layers,
        secondary_ontology_ids=["STATE_OR_SIDE_EFFECT_ERROR"],
        root_cause_hypotheses=diagnosis.root_cause_hypotheses,
        metadata={
            "implicated_tools": diagnosis.implicated_tools,
            "implicated_artifacts": artifact_links,
            "diagnosis": diagnosis.to_dict(),
        },
    )
    return [issue]


def _artifact_links(tool_names: list[str], artifacts: list[HarnessArtifact]) -> list[dict[str, object]]:
    links: list[dict[str, object]] = []
    tool_artifacts = {
        str(artifact.metadata.get("tool_name")): artifact
        for artifact in artifacts
        if artifact.artifact_type == "tool_definition" and artifact.metadata.get("tool_name")
    }

    for tool_name in tool_names:
        tool_artifact = tool_artifacts.get(tool_name)
        if tool_artifact:
            links.append(
                {
                    "artifact_id": tool_artifact.artifact_id,
                    "artifact_type": tool_artifact.artifact_type,
                    "path": tool_artifact.path,
                    "confidence": tool_artifact.confidence,
                    "sha256": tool_artifact.metadata.get("sha256", ""),
                    "reason": f"trace calls side-effecting tool `{tool_name}`",
                }
            )

    for artifact in artifacts:
        if artifact.artifact_type != "permission_policy":
            continue
        governed_tools = set(str(item) for item in artifact.metadata.get("tools", []))
        if governed_tools.intersection(tool_names):
            links.append(
                {
                    "artifact_id": artifact.artifact_id,
                    "artifact_type": artifact.artifact_type,
                    "path": artifact.path,
                    "confidence": artifact.confidence,
                    "sha256": artifact.metadata.get("sha256", ""),
                    "reason": "policy governs an implicated side-effecting tool",
                }
            )

    return links
