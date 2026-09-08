"""Rollback artifact generation for patch bundles."""

from __future__ import annotations

from pathlib import Path
import subprocess

from loopforge.models.patch import PatchBundle
from loopforge.paths import LOCAL_DIR


def reverse_patch_diff(patch: PatchBundle) -> str:
    lines = []
    for line in patch.diff.splitlines(keepends=True):
        if line.startswith("--- "):
            lines.append("+++ " + line[4:])
        elif line.startswith("+++ "):
            lines.append("--- " + line[4:])
        elif line.startswith("+") and not line.startswith("+++"):
            lines.append("-" + line[1:])
        elif line.startswith("-") and not line.startswith("---"):
            lines.append("+" + line[1:])
        else:
            lines.append(line)
    return "".join(lines)


def write_rollback_artifact(root: Path, patch: PatchBundle) -> Path:
    rollback_dir = root / LOCAL_DIR / "rollbacks"
    rollback_dir.mkdir(parents=True, exist_ok=True)
    path = rollback_dir / f"ROLLBACK-{patch.patch_id}.diff"
    path.write_text(reverse_patch_diff(patch), encoding="utf-8")
    return path


def apply_patch_rollback(root: Path, patch: PatchBundle) -> subprocess.CompletedProcess[str]:
    path = write_rollback_artifact(root, patch)
    original_path = root / LOCAL_DIR / "patches" / f"{patch.patch_id}.diff"
    apply_path = original_path if original_path.exists() else path
    return subprocess.run(
        ["git", "apply", "--reverse", str(apply_path)],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
