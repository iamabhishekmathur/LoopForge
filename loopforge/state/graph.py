"""Build and persist harness state snapshots."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

from loopforge.models.harness import HarnessArtifact
from loopforge.models.refinement import RefinementOperation
from loopforge.models.runtime import RuntimeHarnessManifest
from loopforge.models.state import HarnessStateSnapshot
from loopforge.paths import LOCAL_DIR


def build_harness_state_snapshot(
    artifacts: list[HarnessArtifact],
    manifest: RuntimeHarnessManifest,
    *,
    operations: list[RefinementOperation] | None = None,
    parent_state_ids: list[str] | None = None,
    source: str = "codebase_discovery",
    created_at: str | None = None,
) -> HarnessStateSnapshot:
    timestamp = created_at or datetime.now(UTC).isoformat()
    operation_ids = [operation.operation_id for operation in operations or []]
    artifact_refs = [_artifact_ref(artifact) for artifact in artifacts]
    identity = {
        "manifest_id": manifest.manifest_id,
        "artifact_refs": artifact_refs,
        "operation_ids": operation_ids,
        "parents": parent_state_ids or [],
        "source": source,
    }
    state_hash = hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return HarnessStateSnapshot(
        state_id=f"state-{state_hash[:16]}",
        created_at=timestamp,
        source=source,
        artifact_refs=artifact_refs,
        model_config_refs={
            "runtime_manifest_id": manifest.manifest_id,
            "agent_id": manifest.agent_id,
            "agent_version": manifest.agent_version,
            "environment": manifest.environment,
            "model_provider": manifest.model_provider,
            "model_name": manifest.model_name,
            "model_config_hash": manifest.model_config_hash,
        },
        feature_flags=list(manifest.feature_flags),
        experiment_ids=list(manifest.experiment_ids),
        tenant_policy_ids=list(manifest.tenant_policy_ids),
        parent_state_ids=list(parent_state_ids or []),
        operation_ids=operation_ids,
        confidence=_confidence(artifacts, manifest),
        metadata={
            "trace_id": manifest.trace_id,
            "runtime_manifest_id": manifest.manifest_id,
            "artifact_count": len(artifacts),
            "operation_count": len(operation_ids),
            "graph_edges": _graph_edges(artifacts, manifest, operation_ids),
        },
    )


def write_harness_state_snapshot(root: Path, state: HarnessStateSnapshot) -> dict[str, Path]:
    state_dir = root / LOCAL_DIR / "states"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / f"{state.state_id}.json"
    latest_path = state_dir / "latest-harness-state.json"
    payload = json.dumps(state.to_dict(), indent=2, sort_keys=True)
    state_path.write_text(payload, encoding="utf-8")
    latest_path.write_text(payload, encoding="utf-8")
    return {"state": state_path, "latest": latest_path}


def _artifact_ref(artifact: HarnessArtifact) -> dict[str, object]:
    return {
        "artifact_id": artifact.artifact_id,
        "artifact_type": artifact.artifact_type,
        "path": artifact.path,
        "confidence": artifact.confidence,
        "sha256": artifact.metadata.get("sha256", ""),
    }


def _confidence(artifacts: list[HarnessArtifact], manifest: RuntimeHarnessManifest) -> float:
    if not artifacts:
        return 0.0
    artifact_confidence = sum(artifact.confidence for artifact in artifacts) / len(artifacts)
    manifest_bonus = 0.08 if manifest.manifest_id else 0.0
    return round(min(1.0, artifact_confidence + manifest_bonus), 4)


def _graph_edges(
    artifacts: list[HarnessArtifact],
    manifest: RuntimeHarnessManifest,
    operation_ids: list[str],
) -> list[dict[str, str]]:
    edges = [
        {
            "from": manifest.manifest_id,
            "to": artifact.artifact_id,
            "type": "manifest_references_artifact",
        }
        for artifact in artifacts
    ]
    edges.extend(
        {
            "from": operation_id,
            "to": manifest.manifest_id,
            "type": "operation_updates_harness_state",
        }
        for operation_id in operation_ids
    )
    return edges
