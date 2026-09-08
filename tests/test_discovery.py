from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

from loopforge.discovery.scanner import discover_harness_artifacts


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "fixtures" / "support-agent"


def run_loopforge(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "loopforge", *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def copy_fixture(tmp_path: Path) -> Path:
    fixture_root = tmp_path / "fixtures"
    shutil.copytree(
        REPO_ROOT / "fixtures",
        fixture_root,
        ignore=shutil.ignore_patterns(".loopforge"),
    )
    return fixture_root / "support-agent"


def test_discover_harness_artifacts_finds_fixture_harness() -> None:
    artifacts = discover_harness_artifacts(FIXTURE_ROOT)

    by_type = {artifact.artifact_type: artifact for artifact in artifacts}

    assert "system_prompt" in by_type
    assert "tool_definition" in by_type
    assert "permission_policy" in by_type
    assert by_type["tool_definition"].metadata["tool_name"] == "cancel_subscription"
    assert by_type["tool_definition"].metadata["side_effect_class"] == "destructive"
    assert len(by_type["tool_definition"].metadata["sha256"]) == 64
    assert by_type["tool_definition"].metadata["line_count"] > 0
    assert "side_effect_class" in by_type["tool_definition"].metadata["signals"]
    assert by_type["permission_policy"].relationships[0]["type"] == "governs_tool"


def test_discover_command_persists_index_and_artifacts(tmp_path: Path) -> None:
    project_root = copy_fixture(tmp_path)

    result = run_loopforge(["discover"], project_root)

    assert result.returncode == 0, result.stderr
    assert "Discovered 3 harness artifacts" in result.stdout
    assert "manifest:" in result.stdout

    index_path = project_root / ".loopforge" / "index" / "harness-artifacts.json"
    manifest_path = project_root / ".loopforge" / "manifests" / "runtime-harness-manifest.json"
    assert index_path.is_file()
    assert manifest_path.is_file()
    index = json.loads(index_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert index["artifact_count"] == 3
    assert manifest["metadata"]["artifact_count"] == 3
    assert manifest["tool_side_effect_classes"]["cancel_subscription"] == "destructive"

    with sqlite3.connect(project_root / ".loopforge" / "db.sqlite") as connection:
        artifact_count = connection.execute(
            "select count(*) from harness_artifacts"
        ).fetchone()[0]
        manifest_count = connection.execute(
            "select count(*) from runtime_manifests"
        ).fetchone()[0]

    assert artifact_count == 3
    assert manifest_count == 1


def test_manifest_commands_write_and_show_runtime_manifest(tmp_path: Path) -> None:
    project_root = copy_fixture(tmp_path)

    write = run_loopforge(["manifest", "write"], project_root)
    manifest_list = run_loopforge(["manifest", "list"], project_root)
    manifest_show = run_loopforge(["manifest", "show"], project_root)

    assert write.returncode == 0, write.stderr
    assert "Wrote runtime manifest runtime-" in write.stdout
    assert manifest_list.returncode == 0
    assert "artifacts=3" in manifest_list.stdout
    assert manifest_show.returncode == 0
    assert '"tool_side_effect_classes"' in manifest_show.stdout


def test_discover_finds_skill_and_policy_style_artifacts(tmp_path: Path) -> None:
    (tmp_path / "skills").mkdir()
    (tmp_path / "harness").mkdir()
    (tmp_path / "skills" / "cancel.SKILL.md").write_text(
        "# Cancel Skill\n\nUse when cancellation workflow instructions are needed.\n",
        encoding="utf-8",
    )
    (tmp_path / "harness" / "routing_policy.md").write_text(
        "# Routing policy\n\nRoute cancellation workflows carefully.\n",
        encoding="utf-8",
    )
    (tmp_path / "harness" / "context_policy.md").write_text(
        "# Context policy\n\nUse account context before side effects.\n",
        encoding="utf-8",
    )

    artifacts = discover_harness_artifacts(tmp_path)

    assert {artifact.artifact_type for artifact in artifacts} == {
        "skill",
        "routing_policy",
        "context_policy",
    }
