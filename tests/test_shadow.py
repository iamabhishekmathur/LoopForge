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
    shutil.copytree(REPO_ROOT / "fixtures", fixture_root)
    return fixture_root / "support-agent"


def test_shadow_ingests_traces_and_writes_issue_report(tmp_path: Path) -> None:
    project_root = copy_fixture(tmp_path)

    result = run_loopforge(["shadow", "--last", "24h"], project_root)

    assert result.returncode == 0, result.stderr
    assert "traces: 10" in result.stdout
    assert "issues: 1" in result.stdout

    report = project_root / ".loopforge" / "issues" / "ISSUE-0001.md"
    assert report.is_file()
    report_text = report.read_text(encoding="utf-8")
    assert "ACTION_AUTHORIZATION_ERROR" in report_text
    assert "tr_fail_001" in report_text
    assert "tr_clean_001" not in report_text

    db_path = project_root / ".loopforge" / "db.sqlite"
    with sqlite3.connect(db_path) as connection:
        trace_count = connection.execute("select count(*) from traces").fetchone()[0]
        trajectory_count = connection.execute(
            "select count(*) from trace_trajectories"
        ).fetchone()[0]
        issue_count = connection.execute("select count(*) from issues").fetchone()[0]

    assert trace_count == 10
    assert trajectory_count == 10
    assert issue_count == 1


def test_issues_commands_show_shadow_results(tmp_path: Path) -> None:
    project_root = copy_fixture(tmp_path)
    shadow = run_loopforge(["shadow"], project_root)

    issue_list = run_loopforge(["issues", "list"], project_root)
    issue_show = run_loopforge(["issues", "show", "ISSUE-0001"], project_root)

    assert shadow.returncode == 0
    assert issue_list.returncode == 0
    assert "ISSUE-0001" in issue_list.stdout
    assert "ACTION_AUTHORIZATION_ERROR" in issue_show.stdout
