"""Build a behavior map from discovered harness artifacts."""

from __future__ import annotations

import hashlib

from loopforge.models.behavior import AgentBehaviorMap, BehaviorContract
from loopforge.models.harness import HarnessArtifact


def build_behavior_map(artifacts: list[HarnessArtifact]) -> AgentBehaviorMap:
    contracts = [_contract_for_artifact(artifact) for artifact in artifacts]
    tools = [
        {
            "artifact_id": artifact.artifact_id,
            "path": artifact.path,
            "name": artifact.metadata.get("tool_name") or artifact.symbol_or_anchor or artifact.path,
            "side_effect_class": artifact.metadata.get("side_effect_class"),
            "summary": artifact.summary,
        }
        for artifact in artifacts
        if artifact.artifact_type in {"tool_definition", "permission_policy"}
    ]
    artifact_ids = ",".join(sorted(artifact.artifact_id for artifact in artifacts))
    map_id = "behavior-" + hashlib.sha256(artifact_ids.encode("utf-8")).hexdigest()[:16]
    return AgentBehaviorMap(
        map_id=map_id,
        artifact_count=len(artifacts),
        prompt_count=_count(artifacts, "system_prompt"),
        tool_count=_count(artifacts, "tool_definition"),
        skill_count=_count(artifacts, "skill"),
        guardrail_count=sum(1 for artifact in artifacts if "guardrail" in artifact.path.lower()),
        routing_policy_count=_count(artifacts, "routing_policy"),
        context_policy_count=_count(artifacts, "context_policy"),
        contracts=[contract for contract in contracts if contract is not None],
        tool_catalog=tools,
        metadata={
            "artifact_types": sorted({artifact.artifact_type for artifact in artifacts}),
        },
    )


def _count(artifacts: list[HarnessArtifact], artifact_type: str) -> int:
    return sum(1 for artifact in artifacts if artifact.artifact_type == artifact_type)


def _contract_for_artifact(artifact: HarnessArtifact) -> BehaviorContract | None:
    if artifact.artifact_type not in {
        "system_prompt",
        "tool_definition",
        "permission_policy",
        "routing_policy",
        "context_policy",
        "skill",
    }:
        return None
    summary = artifact.summary or f"{artifact.artifact_type} at {artifact.path}"
    evidence = artifact.metadata.get("evidence") or []
    return BehaviorContract(
        contract_id=f"contract_{artifact.artifact_id}",
        contract_type=artifact.artifact_type,
        source_path=artifact.path,
        summary=summary,
        confidence=artifact.confidence,
        metadata={
            "artifact_id": artifact.artifact_id,
            "symbol_or_anchor": artifact.symbol_or_anchor,
            "evidence": evidence,
            "signals": artifact.metadata.get("signals") or [],
            "anchors": artifact.metadata.get("anchors") or [],
        },
    )

