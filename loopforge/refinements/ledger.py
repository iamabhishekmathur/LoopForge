"""Create and persist refinement operations from drafted patches."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from loopforge.models.issue import Issue
from loopforge.models.patch import PatchBundle
from loopforge.models.refinement import RefinementOperation
from loopforge.paths import LOCAL_DIR


def refinement_operations_for_patch(
    issue: Issue,
    patch: PatchBundle,
    *,
    created_at: str | None = None,
) -> list[RefinementOperation]:
    timestamp = created_at or datetime.now(UTC).isoformat()
    operations = []
    for index, artifact in enumerate(patch.target_artifacts, start=1):
        operations.append(
            RefinementOperation(
                operation_id=f"REFINE-{patch.patch_id.removeprefix('PATCH-')}-{index:04d}",
                operation_type="update",
                component_type=_component_type(patch, artifact),
                artifact_id=str(artifact.get("artifact_id") or ""),
                artifact_path=str(artifact.get("path") or ""),
                issue_id=patch.issue_id,
                patch_id=patch.patch_id,
                status="drafted",
                source_trace_ids=list(issue.evidence_trace_ids),
                source_eval_ids=list(patch.new_eval_ids),
                confidence=_operation_confidence(issue, artifact),
                rationale=_rationale(issue, patch, artifact),
                diff_summary=_diff_summary(patch.diff),
                provenance={
                    "ai_observed": True,
                    "ai_drafted": True,
                    "generator": "loopforge.patching.generator",
                    "patch_strategy": patch.metadata.get("strategy"),
                    "patch_layer": patch.metadata.get("patch_layer"),
                    "requires_human_approval": patch.metadata.get(
                        "requires_human_approval",
                        True,
                    ),
                },
                created_at=timestamp,
                metadata={
                    "primary_ontology_id": issue.primary_ontology_id,
                    "issue_confidence": issue.confidence,
                    "artifact_confidence": float(artifact.get("confidence") or 0.0),
                    "target_artifact_type": artifact.get("artifact_type"),
                },
            )
        )
    return operations


def write_refinement_operations(
    root: Path,
    operations: list[RefinementOperation],
) -> list[Path]:
    operation_dir = root / LOCAL_DIR / "refinements"
    operation_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for operation in operations:
        path = operation_dir / f"{operation.operation_id}.json"
        path.write_text(
            json.dumps(operation.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        paths.append(path)
    return paths


def _component_type(patch: PatchBundle, artifact: dict[str, Any]) -> str:
    layer = str(patch.metadata.get("patch_layer") or artifact.get("artifact_type") or "")
    mapping = {
        "system_prompt": "prompt",
        "developer_prompt": "prompt",
        "tool_description": "tool",
        "tool_definition": "tool",
        "permission_policy": "policy",
        "routing_policy": "policy",
        "context_policy": "policy",
        "retrieval_policy": "policy",
        "evaluator": "eval",
        "eval_suite": "eval",
        "skill": "skill",
        "memory": "memory",
        "sub_agent": "sub_agent",
    }
    return mapping.get(layer, "harness_artifact")


def _operation_confidence(issue: Issue, artifact: dict[str, Any]) -> float:
    artifact_confidence = float(artifact.get("confidence") or 0.0)
    if artifact_confidence <= 0:
        return round(issue.confidence, 4)
    return round((issue.confidence + artifact_confidence) / 2, 4)


def _rationale(issue: Issue, patch: PatchBundle, artifact: dict[str, Any]) -> str:
    path = str(artifact.get("path") or "unknown artifact")
    layer = str(patch.metadata.get("patch_layer") or artifact.get("artifact_type") or "harness")
    return (
        f"Trace-backed issue {issue.issue_id} indicates {issue.primary_ontology_id}; "
        f"LoopForge drafted a {layer} refinement for {path} with acceptance gates required "
        "before merge."
    )


def _diff_summary(diff: str) -> str:
    added = sum(1 for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff.splitlines() if line.startswith("-") and not line.startswith("---"))
    return f"{added} additions, {removed} removals"
