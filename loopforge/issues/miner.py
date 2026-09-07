"""Initial issue screener for observable trace failures."""

from __future__ import annotations

from loopforge.models.issue import Issue
from loopforge.models.harness import HarnessArtifact
from loopforge.models.trace import Trace
from loopforge.models.trajectory import TraceTrajectory


SIDE_EFFECT_CLASSES = {"write", "money_movement", "external_message", "destructive"}


def mine_issues(
    traces: list[Trace],
    trajectories: list[TraceTrajectory],
    artifacts: list[HarnessArtifact] | None = None,
) -> list[Issue]:
    """Mine issue candidates from objective trajectory signals.

    This is the local fallback screener. The production screener interface will
    allow model-based classification, but this first implementation only uses
    structured spans, side-effect classes, and feedback.
    """
    trace_by_id = {trace.trace_id: trace for trace in traces}
    evidence_trace_ids: list[str] = []
    implicated_tools: set[str] = set()

    for trajectory in trajectories:
        has_risky_side_effect = any(
            side_effect_class in SIDE_EFFECT_CLASSES
            for side_effect_class in trajectory.side_effect_classes
        )
        has_negative_feedback = "negative_feedback" in trajectory.signals
        if not (has_risky_side_effect and has_negative_feedback):
            continue

        trace = trace_by_id[trajectory.trace_id]
        has_approval = any(span.type == "human_approval" for span in trace.spans)
        if has_approval:
            continue

        evidence_trace_ids.append(trace.trace_id)
        for span in trace.spans:
            if span.type == "tool_call" and span.side_effect_class in SIDE_EFFECT_CLASSES:
                implicated_tools.add(span.name)

    if not evidence_trace_ids:
        return []

    tool_list = sorted(implicated_tools)
    artifact_links = _artifact_links(tool_list, artifacts or [])
    tool_summary = ", ".join(tool_list) if tool_list else "side-effecting tool"
    confidence = min(0.95, 0.68 + (0.05 * len(evidence_trace_ids)))
    severity = "high" if any(
        side_effect in {"money_movement", "destructive"}
        for trajectory in trajectories
        for side_effect in trajectory.side_effect_classes
    ) else "medium"

    issue = Issue(
        issue_id="ISSUE-0001",
        title=f"Side-effecting tool call without approval: {tool_summary}",
        primary_ontology_id="ACTION_AUTHORIZATION_ERROR",
        ontology_version="1",
        failure_layer="governance",
        trace_observability="medium",
        severity=severity,
        confidence=round(confidence, 2),
        evidence_trace_ids=sorted(evidence_trace_ids),
        recommended_patch_layers=["permission_policy", "tool_description", "eval"],
        secondary_ontology_ids=["STATE_OR_SIDE_EFFECT_ERROR"],
        root_cause_hypotheses=[
            {
                "label": "missing_confirmation_contract",
                "confidence": round(confidence, 2),
                "explanation": (
                    "Risky side-effecting tool calls appear in traces with negative "
                    "feedback and no human approval span."
                ),
                "evidence": sorted(evidence_trace_ids),
            }
        ],
        metadata={"implicated_tools": tool_list, "implicated_artifacts": artifact_links},
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
                    "reason": "policy governs an implicated side-effecting tool",
                }
            )

    return links
