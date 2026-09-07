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
    assert by_type["permission_policy"].relationships[0]["type"] == "governs_tool"


def test_discover_command_persists_index_and_artifacts(tmp_path: Path) -> None:
    project_root = copy_fixture(tmp_path)

    result = run_loopforge(["discover"], project_root)

    assert result.returncode == 0, result.stderr
    assert "Discovered 3 harness artifacts" in result.stdout

    index_path = project_root / ".loopforge" / "index" / "harness-artifacts.json"
    assert index_path.is_file()
    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert index["artifact_count"] == 3

    with sqlite3.connect(project_root / ".loopforge" / "db.sqlite") as connection:
        artifact_count = connection.execute(
            "select count(*) from harness_artifacts"
        ).fetchone()[0]

    assert artifact_count == 3
