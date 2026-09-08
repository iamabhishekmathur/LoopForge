from __future__ import annotations

import subprocess
import sys
import os
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


def test_init_creates_project_files(tmp_path: Path) -> None:
    result = run_loopforge(["init", "--project-name", "support-agent"], tmp_path)

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "loopforge.yaml").is_file()
    assert (tmp_path / ".loopforge" / "agent-profile.md").is_file()
    assert (tmp_path / ".loopforge" / "issues").is_dir()
    assert (tmp_path / ".loopforge" / "connectors").is_dir()
    assert (tmp_path / ".loopforge" / "rollbacks").is_dir()
    assert (tmp_path / ".loopforge" / "setup" / "generic-recipe.md").is_file()
    assert "support-agent" in (tmp_path / "loopforge.yaml").read_text(encoding="utf-8")


def test_init_refuses_to_overwrite_existing_config(tmp_path: Path) -> None:
    first = run_loopforge(["init"], tmp_path)
    second = run_loopforge(["init"], tmp_path)

    assert first.returncode == 0
    assert second.returncode == 2
    assert "already exists" in second.stderr


def test_init_scaffolds_framework_recipe(tmp_path: Path) -> None:
    result = run_loopforge(
        ["init", "--project-name", "support-agent", "--framework", "langgraph"],
        tmp_path,
    )

    assert result.returncode == 0, result.stderr
    config = (tmp_path / "loopforge.yaml").read_text(encoding="utf-8")
    recipe = (tmp_path / ".loopforge" / "setup" / "langgraph-recipe.md").read_text(
        encoding="utf-8"
    )
    assert "framework: langgraph" in config
    assert "graph node names" in recipe


def test_doctor_reports_healthy_project(tmp_path: Path) -> None:
    init = run_loopforge(["init"], tmp_path)
    doctor = run_loopforge(["doctor"], tmp_path)

    assert init.returncode == 0
    assert doctor.returncode == 0
    assert "Project health: ok" in doctor.stdout


def test_doctor_fails_outside_project(tmp_path: Path) -> None:
    result = run_loopforge(["doctor"], tmp_path)

    assert result.returncode == 2
    assert "no loopforge.yaml found" in result.stderr


def test_schemas_validate_command(tmp_path: Path) -> None:
    init = run_loopforge(["init"], tmp_path)
    validate = run_loopforge(["schemas", "validate"], tmp_path)

    assert init.returncode == 0
    assert validate.returncode == 0
    assert "trace.schema.json" in validate.stdout


def test_help_includes_discover_and_shadow(tmp_path: Path) -> None:
    result = run_loopforge(["--help"], tmp_path)

    assert result.returncode == 0
    assert "discover" in result.stdout
    assert "onboard" in result.stdout
    assert "readiness" in result.stdout
    assert "demo" in result.stdout
    assert "dashboard" in result.stdout
    assert "manifest" in result.stdout
    assert "states" in result.stdout
    assert "connectors" in result.stdout
    assert "shadow" in result.stdout
    assert "monitor" in result.stdout
    assert "queue" in result.stdout
    assert "learned" in result.stdout
    assert "redact" in result.stdout
    assert "evals" in result.stdout
    assert "propose" in result.stdout
    assert "patches" in result.stdout
    assert "refinements" in result.stdout
    assert "gate" in result.stdout
    assert "pr" in result.stdout
    assert "prs" in result.stdout
    assert "replay" in result.stdout
    assert "confirm" in result.stdout
    assert "confirmations" in result.stdout
    assert "review" in result.stdout
    assert "rollback" in result.stdout
