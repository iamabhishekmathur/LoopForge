from __future__ import annotations

import os
import json
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


def test_shadow_ingests_traces_and_writes_issue_report(tmp_path: Path) -> None:
    project_root = copy_fixture(tmp_path)

    result = run_loopforge(["shadow", "--last", "24h"], project_root)

    assert result.returncode == 0, result.stderr
    assert "traces: 10" in result.stdout
    assert "artifacts: 3" in result.stdout
    assert "issues: 1" in result.stdout
    assert "evals: 1" in result.stdout
    assert "validations: 1" in result.stdout

    report = project_root / ".loopforge" / "issues" / "ISSUE-0001.md"
    assert report.is_file()
    report_text = report.read_text(encoding="utf-8")
    assert "ACTION_AUTHORIZATION_ERROR" in report_text
    assert "tr_fail_001" in report_text
    assert "tr_clean_001" not in report_text
    assert "harness/tools/cancel_subscription.yaml" in report_text
    assert "harness/permissions.yaml" in report_text
    assert ".loopforge/evals/EVAL-0001.json" in report_text

    eval_path = project_root / ".loopforge" / "evals" / "EVAL-0001.json"
    evaluator_path = project_root / ".loopforge" / "evals" / "EVALUATOR-0001.json"
    validation_path = project_root / ".loopforge" / "evals" / "EVALUATOR-0001-validation.json"
    assert eval_path.is_file()
    assert evaluator_path.is_file()
    assert validation_path.is_file()
    eval_payload = json.loads(eval_path.read_text(encoding="utf-8"))
    validation_payload = json.loads(validation_path.read_text(encoding="utf-8"))
    assert {"type": "forbidden_tool_call", "tool": "cancel_subscription"} in eval_payload["assertions"]
    assert validation_payload["validation_status"] == "validated"
    assert validation_payload["blocking_gate_eligible"] is True

    db_path = project_root / ".loopforge" / "db.sqlite"
    with sqlite3.connect(db_path) as connection:
        trace_count = connection.execute("select count(*) from traces").fetchone()[0]
        trajectory_count = connection.execute(
            "select count(*) from trace_trajectories"
        ).fetchone()[0]
        issue_count = connection.execute("select count(*) from issues").fetchone()[0]
        artifact_count = connection.execute(
            "select count(*) from harness_artifacts"
        ).fetchone()[0]
        eval_count = connection.execute("select count(*) from eval_examples").fetchone()[0]
        evaluator_count = connection.execute(
            "select count(*) from evaluator_definitions"
        ).fetchone()[0]
        validation_count = connection.execute(
            "select count(*) from evaluator_validation_records"
        ).fetchone()[0]

    assert trace_count == 10
    assert trajectory_count == 10
    assert issue_count == 1
    assert artifact_count == 3
    assert eval_count == 1
    assert evaluator_count == 1
    assert validation_count == 1


def test_issues_commands_show_shadow_results(tmp_path: Path) -> None:
    project_root = copy_fixture(tmp_path)
    shadow = run_loopforge(["shadow"], project_root)

    issue_list = run_loopforge(["issues", "list"], project_root)
    issue_show = run_loopforge(["issues", "show", "ISSUE-0001"], project_root)
    eval_list = run_loopforge(["evals", "list"], project_root)
    eval_show = run_loopforge(["evals", "show", "EVAL-0001"], project_root)

    assert shadow.returncode == 0
    assert issue_list.returncode == 0
    assert eval_list.returncode == 0
    assert eval_show.returncode == 0
    assert "ISSUE-0001" in issue_list.stdout
    assert "ACTION_AUTHORIZATION_ERROR" in issue_show.stdout
    assert "EVAL-0001" in eval_list.stdout
    assert "forbidden_tool_call" in eval_show.stdout
    assert "Blocking eligible: `True`" in eval_show.stdout
