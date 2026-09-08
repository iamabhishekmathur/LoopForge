"""Runtime manifest helpers for production agent traces."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from loopforge.models.runtime import RuntimeHarnessManifest


@dataclass(frozen=True)
class RuntimeEmitter:
    agent_id: str
    agent_version: str
    model_provider: str
    model_name: str
    environment: str = "production"
    model_config: dict[str, Any] = field(default_factory=dict)
    system_prompt: str = ""
    developer_prompt: str = ""
    skills: dict[str, str] = field(default_factory=dict)
    tool_schemas: dict[str, str] = field(default_factory=dict)
    tool_side_effect_classes: dict[str, str] = field(default_factory=dict)
    eval_suite_versions: dict[str, str] = field(default_factory=dict)
    feature_flags: list[str] = field(default_factory=list)
    experiment_ids: list[str] = field(default_factory=list)
    tenant_policy_ids: list[str] = field(default_factory=list)

    def manifest(self, trace_id: str) -> RuntimeHarnessManifest:
        return build_runtime_manifest(
            trace_id=trace_id,
            agent_id=self.agent_id,
            agent_version=self.agent_version,
            environment=self.environment,
            model_provider=self.model_provider,
            model_name=self.model_name,
            model_config=self.model_config,
            system_prompt=self.system_prompt,
            developer_prompt=self.developer_prompt,
            skills=self.skills,
            tool_schemas=self.tool_schemas,
            tool_side_effect_classes=self.tool_side_effect_classes,
            eval_suite_versions=self.eval_suite_versions,
            feature_flags=self.feature_flags,
            experiment_ids=self.experiment_ids,
            tenant_policy_ids=self.tenant_policy_ids,
        )

    def trace_metadata(self, trace_id: str) -> dict[str, Any]:
        return trace_metadata(self.manifest(trace_id))

    def write_manifest(self, path: Path, trace_id: str) -> Path:
        manifest = self.manifest(trace_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        return path


def build_runtime_manifest(
    trace_id: str,
    agent_id: str,
    agent_version: str,
    environment: str,
    model_provider: str,
    model_name: str,
    model_config: dict[str, Any] | None = None,
    system_prompt: str = "",
    developer_prompt: str = "",
    skills: dict[str, str] | None = None,
    tool_schemas: dict[str, str] | None = None,
    tool_side_effect_classes: dict[str, str] | None = None,
    eval_suite_versions: dict[str, str] | None = None,
    feature_flags: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    tenant_policy_ids: list[str] | None = None,
) -> RuntimeHarnessManifest:
    skills = skills or {}
    tool_schemas = tool_schemas or {}
    manifest_material = {
        "trace_id": trace_id,
        "agent_id": agent_id,
        "agent_version": agent_version,
        "model_provider": model_provider,
        "model_name": model_name,
        "model_config": model_config or {},
        "system_prompt_hash": _hash(system_prompt),
        "developer_prompt_hash": _hash(developer_prompt),
        "skill_versions": {name: _hash(content) for name, content in skills.items()},
        "tool_schema_hashes": {name: _hash(content) for name, content in tool_schemas.items()},
    }
    manifest_id = "runtime-" + _hash(json.dumps(manifest_material, sort_keys=True))[:16]
    return RuntimeHarnessManifest(
        manifest_id=manifest_id,
        trace_id=trace_id,
        agent_id=agent_id,
        agent_version=agent_version,
        environment=environment,
        model_provider=model_provider,
        model_name=model_name,
        model_config_hash=_hash(json.dumps(model_config or {}, sort_keys=True)),
        system_prompt_hash=_hash(system_prompt),
        developer_prompt_hash=_hash(developer_prompt),
        skill_versions={name: _hash(content) for name, content in skills.items()},
        tool_schema_hashes={name: _hash(content) for name, content in tool_schemas.items()},
        tool_side_effect_classes=tool_side_effect_classes or {},
        eval_suite_versions=eval_suite_versions or {},
        feature_flags=feature_flags or [],
        experiment_ids=experiment_ids or [],
        tenant_policy_ids=tenant_policy_ids or [],
        created_at=datetime.now(timezone.utc).isoformat(),
        metadata={"source": "runtime_sdk"},
    )


def trace_metadata(manifest: RuntimeHarnessManifest) -> dict[str, Any]:
    return {
        "runtime_manifest_id": manifest.manifest_id,
        "agent_id": manifest.agent_id,
        "agent_version": manifest.agent_version,
        "model_provider": manifest.model_provider,
        "model_name": manifest.model_name,
        "environment": manifest.environment,
    }


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
