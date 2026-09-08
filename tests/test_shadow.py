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
    assert "structured_probabilistic_v1" in report_text
    assert "Trace scores" in report_text
    assert ".loopforge/analysis/ACTION_AUTHORIZATION_ERROR.json" in report_text

    eval_path = project_root / ".loopforge" / "evals" / "EVAL-0001.json"
    evaluator_path = project_root / ".loopforge" / "evals" / "EVALUATOR-0001.json"
    validation_path = project_root / ".loopforge" / "evals" / "EVALUATOR-0001-validation.json"
    diagnosis_path = project_root / ".loopforge" / "analysis" / "ACTION_AUTHORIZATION_ERROR.json"
    assert eval_path.is_file()
    assert evaluator_path.is_file()
    assert validation_path.is_file()
    assert diagnosis_path.is_file()
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
        issue_payload = json.loads(
            connection.execute(
                "select payload_json from issues where issue_id = 'ISSUE-0001'"
            ).fetchone()[0]
        )
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
        manifest_count = connection.execute(
            "select count(*) from runtime_manifests"
        ).fetchone()[0]
        state_count = connection.execute(
            "select count(*) from harness_states"
        ).fetchone()[0]

    assert trace_count == 10
    assert trajectory_count == 10
    assert issue_count == 1
    assert issue_payload["metadata"]["diagnosis"]["calibration"]["scorer"] == (
        "structured_probabilistic_v1"
    )
    assert artifact_count == 3
    assert eval_count == 1
    assert evaluator_count == 1
    assert validation_count == 1
    assert manifest_count == 1
    assert state_count == 1


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


def test_propose_and_gate_commands_create_patch_and_report(tmp_path: Path) -> None:
    project_root = copy_fixture(tmp_path)
    shadow = run_loopforge(["shadow"], project_root)
    propose = run_loopforge(["propose", "ISSUE-0001"], project_root)
    patches_list = run_loopforge(["patches", "list"], project_root)
    patches_show = run_loopforge(["patches", "show", "PATCH-0001"], project_root)
    refinements_list = run_loopforge(["refinements", "list"], project_root)
    refinements_show = run_loopforge(
        ["refinements", "show", "REFINE-0001-0001"],
        project_root,
    )
    premature_pr = run_loopforge(["pr", "--dry-run", "PATCH-0001"], project_root)
    gate = run_loopforge(["gate", "PATCH-0001"], project_root)
    patches_show_after_gate = run_loopforge(["patches", "show", "PATCH-0001"], project_root)
    pr = run_loopforge(["pr", "--dry-run", "PATCH-0001"], project_root)
    pr_open_disabled = run_loopforge(["pr", "open", "PR-PATCH-0001"], project_root)
    prs_list = run_loopforge(["prs", "list"], project_root)
    prs_show = run_loopforge(["prs", "show", "PR-PATCH-0001"], project_root)

    assert shadow.returncode == 0
    assert propose.returncode == 0, propose.stderr
    assert "Drafted patch PATCH-0001" in propose.stdout
    assert "refiner: tool_refiner" in propose.stdout
    assert "refinements: 1" in propose.stdout
    assert patches_list.returncode == 0
    assert "PATCH-0001" in patches_list.stdout
    assert patches_show.returncode == 0
    assert "explicitly confirmed" in patches_show.stdout
    assert refinements_list.returncode == 0, refinements_list.stderr
    assert "REFINE-0001-0001" in refinements_list.stdout
    assert "tool" in refinements_list.stdout
    assert refinements_show.returncode == 0, refinements_show.stderr
    assert "Trace-backed issue ISSUE-0001" in refinements_show.stdout
    assert "requires_human_approval" in refinements_show.stdout
    assert premature_pr.returncode == 1
    assert "patch must pass gates" in premature_pr.stderr
    assert gate.returncode == 0, gate.stderr
    assert "status: pass" in gate.stdout
    assert "merge_after_human_review" in gate.stdout
    patches_list_after_gate = run_loopforge(["patches", "list"], project_root)
    refinements_show_after_gate = run_loopforge(
        ["refinements", "show", "REFINE-0001-0001"],
        project_root,
    )
    assert "PATCH-0001  gated" in patches_list_after_gate.stdout
    assert patches_show_after_gate.returncode == 0
    assert "Latest Gate" in patches_show_after_gate.stdout
    assert refinements_show_after_gate.returncode == 0, refinements_show_after_gate.stderr
    assert "Status: gated" in refinements_show_after_gate.stdout
    assert pr.returncode == 0, pr.stderr
    assert "Drafted PR artifact PR-PATCH-0001" in pr.stdout
    assert "loopforge/issue-0001/cancel-subscription" in pr.stdout
    assert pr_open_disabled.returncode == 1
    assert "open_prs is false" in pr_open_disabled.stderr
    assert prs_list.returncode == 0
    assert "PR-PATCH-0001" in prs_list.stdout
    assert prs_show.returncode == 0
    assert "Gate Results" in prs_show.stdout
    assert "Evaluator Validation" in prs_show.stdout
    assert "requires_human_approval" not in prs_show.stdout

    assert (project_root / ".loopforge" / "patches" / "PATCH-0001.json").is_file()
    assert (project_root / ".loopforge" / "patches" / "PATCH-0001.diff").is_file()
    assert (
        project_root / ".loopforge" / "refinements" / "REFINE-0001-0001.json"
    ).is_file()
    assert (project_root / ".loopforge" / "reports" / "GATE-PATCH-0001.json").is_file()
    assert (project_root / ".loopforge" / "reports" / "REPLAY-PATCH-0001.json").is_file()
    assert (project_root / ".loopforge" / "prs" / "PR-PATCH-0001.json").is_file()
    assert (project_root / ".loopforge" / "prs" / "PR-PATCH-0001.md").is_file()

    pr_payload = json.loads(
        (project_root / ".loopforge" / "prs" / "PR-PATCH-0001.json").read_text(
            encoding="utf-8"
        )
    )
    assert pr_payload["metadata"]["requires_human_approval"] is True
    assert "GATE-PATCH-0001" in pr_payload["body"] or "Gate Results" in pr_payload["body"]

    refinement_payload = json.loads(
        (
            project_root / ".loopforge" / "refinements" / "REFINE-0001-0001.json"
        ).read_text(encoding="utf-8")
    )
    assert refinement_payload["component_type"] == "tool"
    assert refinement_payload["patch_id"] == "PATCH-0001"
    assert refinement_payload["status"] == "gated"
    assert refinement_payload["provenance"]["component_pass"] == "tool_refiner"
    assert refinement_payload["metadata"]["latest_gate_status"] == "pass"
