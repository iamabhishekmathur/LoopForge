from __future__ import annotations

import os
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


def test_demo_command_creates_runnable_project(tmp_path: Path) -> None:
    result = run_loopforge(["demo", "--path", "demo-agent"], tmp_path)

    assert result.returncode == 0, result.stderr
    assert "Created LoopForge demo" in result.stdout
    assert "ISSUE-0001" in result.stdout
    assert "PATCH-0001" in result.stdout
    demo_root = tmp_path / "demo-agent"
    assert (demo_root / "loopforge.yaml").is_file()
    assert (demo_root / ".loopforge" / "patches" / "PATCH-0001.json").is_file()
    assert (demo_root / ".loopforge" / "reports" / "GATE-PATCH-0001.json").is_file()

    preview = run_loopforge(
        ["refinements", "preview", "REFINE-0001-0001"],
        demo_root,
    )

    assert preview.returncode == 0, preview.stderr
    assert "Diff Preview" in preview.stdout


def test_demo_command_refuses_existing_directory(tmp_path: Path) -> None:
    (tmp_path / "demo-agent").mkdir()

    result = run_loopforge(["demo", "--path", "demo-agent"], tmp_path)

    assert result.returncode == 2
    assert "already exists" in result.stderr
