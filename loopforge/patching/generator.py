"""Generate local patch bundles from grounded issues."""

from __future__ import annotations

import difflib
import hashlib
import json
from pathlib import Path

from loopforge.models.issue import Issue
from loopforge.models.patch import PatchBundle
from loopforge.paths import LOCAL_DIR


def generate_patch_for_issue(
    root: Path,
    issue: Issue,
    eval_ids: list[str],
    preferred_layer: str | None = None,
) -> PatchBundle | None:
    if issue.primary_ontology_id != "ACTION_AUTHORIZATION_ERROR":
        return None

    if preferred_layer == "permission_policy":
        return _permission_policy_patch(root, issue, eval_ids)
    if preferred_layer in {
        "system_prompt",
        "skill",
        "routing_policy",
        "context_policy",
        "retrieval_policy",
        "evaluator",
    }:
        return _generic_guidance_patch(root, issue, eval_ids, preferred_layer)
    if preferred_layer == "tool_description" or preferred_layer is None:
        patch = _tool_description_patch(root, issue, eval_ids)
        if patch is not None or preferred_layer == "tool_description":
            return patch
    return _permission_policy_patch(root, issue, eval_ids)


def _tool_description_patch(
    root: Path,
    issue: Issue,
    eval_ids: list[str],
) -> PatchBundle | None:
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
                "sha256": _artifact_sha(root, tool_artifact),
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
            "diagnosis_confidence": issue.confidence,
            "requires_human_approval": True,
        },
    )


def _permission_policy_patch(
    root: Path,
    issue: Issue,
    eval_ids: list[str],
) -> PatchBundle | None:
    policy_artifact = _first_artifact(issue, "permission_policy")
    if policy_artifact is None:
        return None

    target_path = root / str(policy_artifact["path"])
    original = target_path.read_text(encoding="utf-8")
    patched = _patch_permission_policy(original, issue)
    if patched == original:
        return None

    diff = _unified_diff(str(policy_artifact["path"]), original, patched)
    return PatchBundle(
        patch_id=f"PATCH-{issue.issue_id.removeprefix('ISSUE-')}",
        issue_id=issue.issue_id,
        target_artifacts=[
            {
                "artifact_id": str(policy_artifact["artifact_id"]),
                "artifact_type": str(policy_artifact["artifact_type"]),
                "path": str(policy_artifact["path"]),
                "confidence": float(policy_artifact.get("confidence") or 0),
                "sha256": _artifact_sha(root, policy_artifact),
            }
        ],
        diff=diff,
        new_eval_ids=eval_ids,
        risk_assessment=(
            "Medium-risk permission-policy patch. It changes governance behavior "
            "for an implicated side-effecting tool and should require replay."
        ),
        rollback_plan="Revert the permission policy change and keep the generated eval as coverage.",
        metadata={
            "strategy": "governance_policy_patch",
            "ai_drafted": True,
            "patch_layer": "permission_policy",
            "diagnosis_confidence": issue.confidence,
            "requires_human_approval": True,
        },
    )


def _generic_guidance_patch(
    root: Path,
    issue: Issue,
    eval_ids: list[str],
    layer: str,
) -> PatchBundle | None:
    artifact_type = "eval_suite" if layer == "evaluator" else layer
    artifact = _first_artifact(issue, artifact_type)
    if artifact is None and layer == "system_prompt":
        artifact = _first_artifact(issue, "system_prompt")
    if artifact is None:
        return None

    path = root / str(artifact["path"])
    original = path.read_text(encoding="utf-8")
    patched = _append_guidance(original, issue, layer)
    if patched == original:
        return None
    diff = _unified_diff(str(artifact["path"]), original, patched)
    return PatchBundle(
        patch_id=f"PATCH-{issue.issue_id.removeprefix('ISSUE-')}",
        issue_id=issue.issue_id,
        target_artifacts=[
            {
                "artifact_id": str(artifact["artifact_id"]),
                "artifact_type": str(artifact["artifact_type"]),
                "path": str(artifact["path"]),
                "confidence": float(artifact.get("confidence") or 0),
                "sha256": _artifact_sha(root, artifact),
            }
        ],
        diff=diff,
        new_eval_ids=eval_ids,
        risk_assessment=(
            f"Medium-risk {layer} patch. It adds narrowly scoped guidance for "
            "an observed failure and should be reviewed against regressions."
        ),
        rollback_plan=f"Revert the {layer} guidance change and keep the generated eval as coverage.",
        metadata={
            "strategy": f"{layer}_guidance_patch",
            "ai_drafted": True,
            "patch_layer": layer,
            "diagnosis_confidence": issue.confidence,
            "requires_human_approval": True,
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


def _unified_diff(path: str, original: str, patched: str) -> str:
    return "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            patched.splitlines(keepends=True),
            fromfile=path,
            tofile=path,
        )
    )


def _artifact_sha(root: Path, artifact: dict[str, object]) -> str:
    existing = str(artifact.get("sha256") or "")
    if existing:
        return existing
    path = root / str(artifact.get("path") or "")
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def _patch_permission_policy(content: str, issue: Issue) -> str:
    tools = issue.metadata.get("implicated_tools", [])
    if not isinstance(tools, list) or not tools:
        return content
    tool_name = str(tools[0])
    lines = content.splitlines()
    patched_lines = []
    inside_tool = False
    changed = False
    for line in lines:
        stripped = line.strip()
        if stripped == f"{tool_name}:":
            inside_tool = True
            patched_lines.append(line)
            continue
        if inside_tool and line.startswith("  ") and stripped.startswith("requires_confirmation:"):
            patched_lines.append("    requires_confirmation: true")
            changed = stripped != "requires_confirmation: true"
            continue
        if inside_tool and not line.startswith("    ") and stripped:
            inside_tool = False
        patched_lines.append(line)
    return "\n".join(patched_lines) + "\n" if changed else content


def _append_guidance(content: str, issue: Issue, layer: str) -> str:
    tools = issue.metadata.get("implicated_tools", [])
    tool = str(tools[0]) if isinstance(tools, list) and tools else "side-effecting tool"
    marker = f"LoopForge guidance: {issue.primary_ontology_id}"
    if marker in content:
        return content
    guidance = (
        f"\n\n## {marker}\n\n"
        f"When using `{tool}`, treat destructive or externally visible actions as "
        "requiring explicit user confirmation in the current interaction before "
        "execution. Prefer a clarification or draft response when confirmation is "
        "ambiguous. This guidance was generated for `{layer}` from trace-backed "
        f"evidence: {', '.join(issue.evidence_trace_ids)}.\n"
    )
    return content.rstrip() + guidance
