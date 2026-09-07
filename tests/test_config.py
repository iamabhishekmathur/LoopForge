from __future__ import annotations

from pathlib import Path

from loopforge.config import (
    InitOptions,
    configured_max_prs_per_day,
    configured_open_prs,
    initialize_project,
    inspect_project,
)


def test_initialize_project_is_inspectable(tmp_path: Path) -> None:
    initialize_project(tmp_path, InitOptions(project_name="fixture-agent"))

    status = inspect_project(tmp_path)

    assert all(status.values())
    assert "fixture-agent" in (tmp_path / "loopforge.yaml").read_text(encoding="utf-8")


def test_pr_opening_config_defaults_to_disabled(tmp_path: Path) -> None:
    initialize_project(tmp_path, InitOptions(project_name="fixture-agent"))

    assert configured_open_prs(tmp_path) is False
    assert configured_max_prs_per_day(tmp_path) == 3


def test_pr_opening_uses_default_daily_cap_when_missing(tmp_path: Path) -> None:
    (tmp_path / "loopforge.yaml").write_text(
        "monitor:\n  open_prs: true\n",
        encoding="utf-8",
    )

    assert configured_open_prs(tmp_path) is True
    assert configured_max_prs_per_day(tmp_path) == 3
