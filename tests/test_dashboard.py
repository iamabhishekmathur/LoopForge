from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from loopforge.dashboard.render import render_dashboard


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


def test_render_dashboard_escapes_issue_content() -> None:
    html = render_dashboard(
        {
            "project_root": "/repo",
            "connectors": [],
            "monitor_runs": [],
            "issues": [
                {
                    "issue_id": "ISSUE-1",
                    "severity": "high",
                    "confidence": 0.9,
                    "primary_ontology_id": "X",
                    "title": "<script>alert(1)</script>",
                }
            ],
            "evals": [],
            "patches": [],
            "gates": [],
            "prs": [],
            "manifests": [],
        }
    )

    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_dashboard_build_writes_fixture_html(tmp_path: Path) -> None:
    project_root = copy_fixture(tmp_path)
    onboard = run_loopforge(["onboard"], project_root)

    result = run_loopforge(["dashboard", "build"], project_root)

    assert onboard.returncode == 0
    assert result.returncode == 0, result.stderr
    assert "Built dashboard .loopforge/dashboard.html" in result.stdout
    html = (project_root / ".loopforge" / "dashboard.html").read_text(encoding="utf-8")
    assert "LoopForge Dashboard" in html
    assert "ISSUE-0001" in html
    assert "Monitor Runs" in html
