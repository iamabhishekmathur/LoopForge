from __future__ import annotations

from pathlib import Path

from loopforge.config import InitOptions, initialize_project, inspect_project


def test_initialize_project_is_inspectable(tmp_path: Path) -> None:
    initialize_project(tmp_path, InitOptions(project_name="fixture-agent"))

    status = inspect_project(tmp_path)

    assert all(status.values())
    assert "fixture-agent" in (tmp_path / "loopforge.yaml").read_text(encoding="utf-8")
