"""Runtime harness manifest model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RuntimeHarnessManifest:
    manifest_id: str
    trace_id: str
    agent_id: str
    agent_version: str
    environment: str
    model_provider: str
    model_name: str
    created_at: str
    model_config_hash: str = ""
    system_prompt_hash: str = ""
    developer_prompt_hash: str = ""
    skill_versions: dict[str, str] = field(default_factory=dict)
    tool_schema_hashes: dict[str, str] = field(default_factory=dict)
    tool_implementation_versions: dict[str, str] = field(default_factory=dict)
    tool_side_effect_classes: dict[str, str] = field(default_factory=dict)
    router_policy_hash: str = ""
    permission_policy_hash: str = ""
    context_policy_hash: str = ""
    retrieval_policy_hash: str = ""
    memory_policy_hash: str = ""
    feature_flags: list[str] = field(default_factory=list)
    experiment_ids: list[str] = field(default_factory=list)
    tenant_policy_ids: list[str] = field(default_factory=list)
    prompt_registry_refs: list[dict[str, str]] = field(default_factory=list)
    eval_suite_versions: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuntimeHarnessManifest":
        return cls(
            manifest_id=str(data["manifest_id"]),
            trace_id=str(data["trace_id"]),
            agent_id=str(data["agent_id"]),
            agent_version=str(data["agent_version"]),
            environment=str(data["environment"]),
            model_provider=str(data["model_provider"]),
            model_name=str(data["model_name"]),
            created_at=str(data["created_at"]),
            model_config_hash=str(data.get("model_config_hash") or ""),
            system_prompt_hash=str(data.get("system_prompt_hash") or ""),
            developer_prompt_hash=str(data.get("developer_prompt_hash") or ""),
            skill_versions=dict(data.get("skill_versions") or {}),
            tool_schema_hashes=dict(data.get("tool_schema_hashes") or {}),
            tool_implementation_versions=dict(data.get("tool_implementation_versions") or {}),
            tool_side_effect_classes=dict(data.get("tool_side_effect_classes") or {}),
            router_policy_hash=str(data.get("router_policy_hash") or ""),
            permission_policy_hash=str(data.get("permission_policy_hash") or ""),
            context_policy_hash=str(data.get("context_policy_hash") or ""),
            retrieval_policy_hash=str(data.get("retrieval_policy_hash") or ""),
            memory_policy_hash=str(data.get("memory_policy_hash") or ""),
            feature_flags=list(data.get("feature_flags") or []),
            experiment_ids=list(data.get("experiment_ids") or []),
            tenant_policy_ids=list(data.get("tenant_policy_ids") or []),
            prompt_registry_refs=list(data.get("prompt_registry_refs") or []),
            eval_suite_versions=dict(data.get("eval_suite_versions") or {}),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "manifest_id": self.manifest_id,
            "trace_id": self.trace_id,
            "agent_id": self.agent_id,
            "agent_version": self.agent_version,
            "environment": self.environment,
            "model_provider": self.model_provider,
            "model_name": self.model_name,
            "model_config_hash": self.model_config_hash,
            "system_prompt_hash": self.system_prompt_hash,
            "developer_prompt_hash": self.developer_prompt_hash,
            "skill_versions": self.skill_versions,
            "tool_schema_hashes": self.tool_schema_hashes,
            "tool_implementation_versions": self.tool_implementation_versions,
            "tool_side_effect_classes": self.tool_side_effect_classes,
            "router_policy_hash": self.router_policy_hash,
            "permission_policy_hash": self.permission_policy_hash,
            "context_policy_hash": self.context_policy_hash,
            "retrieval_policy_hash": self.retrieval_policy_hash,
            "memory_policy_hash": self.memory_policy_hash,
            "feature_flags": self.feature_flags,
            "experiment_ids": self.experiment_ids,
            "tenant_policy_ids": self.tenant_policy_ids,
            "prompt_registry_refs": self.prompt_registry_refs,
            "eval_suite_versions": self.eval_suite_versions,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }
