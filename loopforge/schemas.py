"""Schema discovery and parse validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .paths import schema_dir


@dataclass(frozen=True)
class SchemaStatus:
    path: Path
    valid: bool
    error: str | None = None


def iter_schema_paths(root: Path | None = None) -> list[Path]:
    directory = root or schema_dir()
    return sorted(directory.glob("*.schema.json"))


def validate_schema_parse(path: Path) -> SchemaStatus:
    try:
        with path.open("r", encoding="utf-8") as handle:
            schema = json.load(handle)
    except Exception as exc:  # pragma: no cover - exact parser errors vary.
        return SchemaStatus(path=path, valid=False, error=str(exc))

    missing = [key for key in ("$schema", "title", "type", "properties") if key not in schema]
    if missing:
        return SchemaStatus(
            path=path,
            valid=False,
            error=f"missing required schema metadata: {', '.join(missing)}",
        )
    return SchemaStatus(path=path, valid=True)


def validate_all_schemas(root: Path | None = None) -> list[SchemaStatus]:
    return [validate_schema_parse(path) for path in iter_schema_paths(root)]
