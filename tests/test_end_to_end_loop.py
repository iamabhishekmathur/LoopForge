from __future__ import annotations

import os
import shutil
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


def test_monitor_to_rollback_closed_loop_fixture(tmp_path: Path) -> None:
    project_root = copy_fixture(tmp_path)

    steps = [
        run_loopforge(["monitor", "--once", "--last", "24h"], project_root),
        run_loopforge(["queue", "run-next"], project_root),
        run_loopforge(["propose", "ISSUE-0001"], project_root),
        run_loopforge(["refinements", "preview", "REFINE-0001-0001"], project_root),
        run_loopforge(["gate", "PATCH-0001"], project_root),
        run_loopforge(["pr", "--dry-run", "PATCH-0001"], project_root),
        run_loopforge(
            ["confirm", "PATCH-0001", "--observed-traces", "20", "--recurring-failures", "0"],
            project_root,
        ),
        run_loopforge(["review", "REFINE-0001-0001", "merged"], project_root),
        run_loopforge(["learned"], project_root),
        run_loopforge(["rollback", "PATCH-0001"], project_root),
    ]

    assert all(step.returncode == 0 for step in steps), [step.stderr for step in steps]
    assert "Status: `succeeded`" in steps[1].stdout
    assert "Diff Preview" in steps[3].stdout
    assert "status: pass" in steps[4].stdout
    assert "Drafted PR artifact PR-PATCH-0001" in steps[5].stdout
    assert "outcome: confirmed" in steps[6].stdout
    assert "What LoopForge Learned" in steps[8].stdout
    assert "Wrote rollback artifact" in steps[9].stdout
