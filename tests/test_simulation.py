from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_support_cancel_agent_simulation_runs_end_to_end(tmp_path: Path) -> None:
    simulation_root = tmp_path / "support-cancel-agent"
    shutil.copytree(
        REPO_ROOT / "simulations" / "support-cancel-agent",
        simulation_root,
        ignore=shutil.ignore_patterns(".loopforge", "simulation-output.md"),
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)

    result = subprocess.run(
        [sys.executable, str(simulation_root / "run_simulation.py")],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    output = (simulation_root / "simulation-output.md").read_text(encoding="utf-8")
    assert "simulated-langsmith" in output
    assert "Monitor run MONITOR-" in output
    assert "traces=6 issues=1 evals=1 validations=1" in output
    assert "Status: `validated`" in output
    assert "recommendation: merge_after_human_review" in output
    assert "Drafted PR artifact PR-PATCH-0001" in output


def test_acme_agent_platform_simulation_runs_end_to_end(tmp_path: Path) -> None:
    simulation_root = tmp_path / "acme-agent-platform"
    shutil.copytree(
        REPO_ROOT / "simulations" / "acme-agent-platform",
        simulation_root,
        ignore=shutil.ignore_patterns(".loopforge", "simulation-output.md"),
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)

    result = subprocess.run(
        [sys.executable, str(simulation_root / "run_simulation.py")],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    output = (simulation_root / "simulation-output.md").read_text(encoding="utf-8")
    assert "acme-langsmith" in output
    assert "Monitor run MONITOR-" in output
    assert "traces=12 issues=1 evals=1 validations=1 resolutions=1" in output
    assert "Side-effecting tool call without approval: cancel_subscription" in output
    assert "runtime_enforcement_gap" in output
    assert "policy already indicates confirmation is required" in output
    assert "Status: `validated`" in output
    assert "recommendation: merge_after_human_review" in output
    assert "Retrieval misses and escalation noise are intentionally present" in output
