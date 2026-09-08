"""Harness state graph models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class HarnessStateSnapshot:
    state_id: str
    created_at: str
    source: str
    artifact_refs: list[dict[str, Any]]
    model_config_refs: dict[str, Any]
    feature_flags: list[str]
    experiment_ids: list[str]
    tenant_policy_ids: list[str]
    parent_state_ids: list[str]
    operation_ids: list[str]
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HarnessStateSnapshot":
        return cls(
            state_id=str(data["state_id"]),
            created_at=str(data["created_at"]),
            source=str(data["source"]),
            artifact_refs=list(data.get("artifact_refs") or []),
            model_config_refs=dict(data.get("model_config_refs") or {}),
            feature_flags=list(data.get("feature_flags") or []),
            experiment_ids=list(data.get("experiment_ids") or []),
            tenant_policy_ids=list(data.get("tenant_policy_ids") or []),
            parent_state_ids=list(data.get("parent_state_ids") or []),
            operation_ids=list(data.get("operation_ids") or []),
            confidence=float(data.get("confidence") or 0.0),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "state_id": self.state_id,
            "created_at": self.created_at,
            "source": self.source,
            "artifact_refs": self.artifact_refs,
            "model_config_refs": self.model_config_refs,
            "feature_flags": self.feature_flags,
            "experiment_ids": self.experiment_ids,
            "tenant_policy_ids": self.tenant_policy_ids,
            "parent_state_ids": self.parent_state_ids,
            "operation_ids": self.operation_ids,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }
