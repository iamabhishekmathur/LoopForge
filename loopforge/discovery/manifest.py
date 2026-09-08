"""Runtime harness manifest generation from discovered codebase artifacts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from loopforge.models.harness import HarnessArtifact
from loopforge.models.runtime import RuntimeHarnessManifest
from loopforge.paths import LOCAL_DIR


def build_runtime_manifest(root: Path, artifacts: list[HarnessArtifact]) -> RuntimeHarnessManifest:
    created_at = datetime.now(timezone.utc).isoformat()
    artifact_hashes = {
        artifact.artifact_id: str(artifact.metadata.get("sha256") or "")
        for artifact in artifacts
    }
    manifest_hash = _hash("|".join(sorted(artifact_hashes.values())))
    tool_artifacts = [
        artifact for artifact in artifacts if artifact.artifact_type == "tool_definition"
    ]
    permission_artifacts = [
        artifact for artifact in artifacts if artifact.artifact_type == "permission_policy"
    ]
    system_artifact = _first_artifact(artifacts, "system_prompt")

    return RuntimeHarnessManifest(
        manifest_id=f"runtime-{manifest_hash[:16]}",
        trace_id="static-codebase-index",
        agent_id=root.name,
        agent_version="unknown",
        environment="local",
        model_provider="unknown",
        model_name="unknown",
        created_at=created_at,
        system_prompt_hash=_artifact_hash(system_artifact),
        tool_schema_hashes={
            str(artifact.metadata.get("tool_name") or artifact.artifact_id): _artifact_hash(artifact)
            for artifact in tool_artifacts
        },
        tool_side_effect_classes={
            str(artifact.metadata.get("tool_name") or artifact.artifact_id): str(
                artifact.metadata.get("side_effect_class") or "unknown"
            )
            for artifact in tool_artifacts
        },
        permission_policy_hash=_artifact_hash(permission_artifacts[0])
        if permission_artifacts
        else "",
        metadata={
            "source": "codebase_discovery",
            "artifact_count": len(artifacts),
            "artifact_hashes": artifact_hashes,
            "artifact_paths": {
                artifact.artifact_id: artifact.path for artifact in artifacts
            },
        },
    )


def write_runtime_manifest(root: Path, manifest: RuntimeHarnessManifest) -> Path:
    manifest_dir = root / LOCAL_DIR / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    path = manifest_dir / "runtime-harness-manifest.json"
    path.write_text(json.dumps(manifest.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return path


def _first_artifact(
    artifacts: list[HarnessArtifact],
    artifact_type: str,
) -> HarnessArtifact | None:
    for artifact in artifacts:
        if artifact.artifact_type == artifact_type:
            return artifact
    return None


def _artifact_hash(artifact: HarnessArtifact | None) -> str:
    if artifact is None:
        return ""
    return str(artifact.metadata.get("sha256") or "")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
