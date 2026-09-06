"""Filesystem path helpers for LoopForge projects."""

from __future__ import annotations

from pathlib import Path


PROJECT_CONFIG = "loopforge.yaml"
LOCAL_DIR = ".loopforge"


def find_project_root(start: Path | None = None) -> Path | None:
    """Walk upward from `start` until a LoopForge project config is found."""
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / PROJECT_CONFIG).is_file():
            return candidate
    return None


def require_project_root(start: Path | None = None) -> Path:
    root = find_project_root(start)
    if root is None:
        raise FileNotFoundError(
            f"No {PROJECT_CONFIG} found. Run `loopforge init` from a project root."
        )
    return root


def package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def schema_dir() -> Path:
    return package_root() / "schemas"
