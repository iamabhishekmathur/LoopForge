from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


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


def test_onboard_runs_discovery_manifest_and_monitor(tmp_path: Path) -> None:
    project_root = copy_fixture(tmp_path)

    result = run_loopforge(["onboard"], project_root)

    assert result.returncode == 0, result.stderr
    assert "Using LoopForge project" in result.stdout
    assert "Connectors: 1/1 ready" in result.stdout
    assert "Discovery: 3 artifacts" in result.stdout
    assert "Monitor run MONITOR-" in result.stdout
    assert "Onboarding complete." in result.stdout

    with sqlite3.connect(project_root / ".loopforge" / "db.sqlite") as connection:
        run_count = connection.execute("select count(*) from monitor_runs").fetchone()[0]
        manifest_count = connection.execute(
            "select count(*) from runtime_manifests"
        ).fetchone()[0]

    assert run_count == 1
    assert manifest_count == 1


def test_onboard_can_skip_monitor_for_empty_projects(tmp_path: Path) -> None:
    result = run_loopforge(
        ["onboard", "--project-name", "empty-agent", "--skip-monitor"],
        tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "loopforge.yaml").is_file()
    assert "Initialized LoopForge project" in result.stdout
    assert "Monitor: skipped" in result.stdout
