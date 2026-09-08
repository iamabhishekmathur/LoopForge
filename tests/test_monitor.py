from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from loopforge.monitor.runner import parse_schedule_seconds


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


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("30s", 30),
        ("every 5 minutes", 300),
        ("2h", 7200),
    ],
)
def test_parse_schedule_seconds(value: str, expected: float) -> None:
    assert parse_schedule_seconds(value) == expected


def test_parse_schedule_seconds_rejects_unknown_shape() -> None:
    with pytest.raises(ValueError, match="unsupported monitor schedule"):
        parse_schedule_seconds("weekdays at noon")


def test_monitor_once_records_run_and_history(tmp_path: Path) -> None:
    project_root = copy_fixture(tmp_path)

    run = run_loopforge(["monitor", "--once", "--last", "24h"], project_root)

    assert run.returncode == 0, run.stderr
    assert "Monitor run MONITOR-" in run.stdout
    assert "succeeded" in run.stdout
    assert "traces=10" in run.stdout
    assert "issues=1" in run.stdout

    db_path = project_root / ".loopforge" / "db.sqlite"
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "select run_id, status from monitor_runs"
        ).fetchone()
    assert row[1] == "succeeded"

    list_runs = run_loopforge(["monitor", "--list-runs"], project_root)
    show_run = run_loopforge(["monitor", "--show-run", row[0]], project_root)

    assert list_runs.returncode == 0
    assert row[0] in list_runs.stdout
    assert show_run.returncode == 0
    assert "Status: `succeeded`" in show_run.stdout
    assert "traces: `10`" in show_run.stdout
