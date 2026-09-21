"""Codebase-derived behavior map models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BehaviorContract:
    contract_id: str
    contract_type: str
    source_path: str
    summary: str
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "contract_type": self.contract_type,
            "source_path": self.source_path,
            "summary": self.summary,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class AgentBehaviorMap:
    map_id: str
    artifact_count: int
    prompt_count: int
    tool_count: int
    skill_count: int
    guardrail_count: int
    routing_policy_count: int
    context_policy_count: int
    contracts: list[BehaviorContract]
    tool_catalog: list[dict[str, Any]]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "map_id": self.map_id,
            "artifact_count": self.artifact_count,
            "prompt_count": self.prompt_count,
            "tool_count": self.tool_count,
            "skill_count": self.skill_count,
            "guardrail_count": self.guardrail_count,
            "routing_policy_count": self.routing_policy_count,
            "context_policy_count": self.context_policy_count,
            "contracts": [contract.to_dict() for contract in self.contracts],
            "tool_catalog": self.tool_catalog,
            "metadata": self.metadata,
        }

