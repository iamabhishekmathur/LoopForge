"""Generate local patch bundles from grounded issues."""

from __future__ import annotations

import difflib
import json
from pathlib import Path

from loopforge.models.issue import Issue
from loopforge.models.patch import PatchBundle
from loopforge.paths import LOCAL_DIR


def generate_patch_for_issue(
    root: Path,
    issue: Issue,
    eval_ids: list[str],
) -> PatchBundle | None:
    if issue.primary_ontology_id != "ACTION_AUTHORIZATION_ERROR":
        return None

    tool_artifact = _first_artifact(issue, "tool_definition")
    if tool_artifact is None:
        return None

    target_path = root / str(tool_artifact["path"])
    original = target_path.read_text(encoding="utf-8")
    patched = _patch_tool_description(original)
    if patched == original:
        return None

    diff = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            patched.splitlines(keepends=True),
            fromfile=str(tool_artifact["path"]),
            tofile=str(tool_artifact["path"]),
        )
    )
    return PatchBundle(
        patch_id=f"PATCH-{issue.issue_id.removeprefix('ISSUE-')}",
        issue_id=issue.issue_id,
        target_artifacts=[
            {
                "artifact_id": str(tool_artifact["artifact_id"]),
                "artifact_type": str(tool_artifact["artifact_type"]),
                "path": str(tool_artifact["path"]),
                "confidence": float(tool_artifact.get("confidence") or 0),
            }
        ],
        diff=diff,
        new_eval_ids=eval_ids,
        risk_assessment=(
            "Low-risk tool-description patch. It narrows when a destructive "
            "tool should be called and relies on existing confirmation policy."
        ),
        rollback_plan="Revert the tool description change and keep the generated eval as coverage.",
        metadata={
            "strategy": "smallest_grounded_patch",
            "ai_drafted": True,
            "patch_layer": "tool_description",
        },
    )


def write_patch_bundle(root: Path, patch: PatchBundle) -> dict[str, Path]:
    patch_dir = root / LOCAL_DIR / "patches"
    patch_dir.mkdir(parents=True, exist_ok=True)
    json_path = patch_dir / f"{patch.patch_id}.json"
    diff_path = patch_dir / f"{patch.patch_id}.diff"
    json_path.write_text(json.dumps(patch.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    diff_path.write_text(patch.diff, encoding="utf-8")
    return {"json": json_path, "diff": diff_path}


def _first_artifact(issue: Issue, artifact_type: str) -> dict[str, object] | None:
    artifacts = issue.metadata.get("implicated_artifacts", [])
    if not isinstance(artifacts, list):
        return None
    for artifact in artifacts:
        if isinstance(artifact, dict) and artifact.get("artifact_type") == artifact_type:
            return artifact
    return None


def _patch_tool_description(content: str) -> str:
    replacement = (
        "description: Cancel a customer's active subscription only after the "
        "user has explicitly confirmed they want cancellation to happen now."
    )
    lines = content.splitlines()
    patched_lines = []
    replaced = False
    for line in lines:
        if line.startswith("description:"):
            patched_lines.append(replacement)
            replaced = True
        else:
            patched_lines.append(line)
    if not replaced:
        patched_lines.insert(1, replacement)
    return "\n".join(patched_lines) + "\n"
