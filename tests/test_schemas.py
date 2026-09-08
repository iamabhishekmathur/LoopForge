from __future__ import annotations

import json
from pathlib import Path

from loopforge.schemas import iter_schema_paths, validate_all_schemas


def test_all_schema_files_parse() -> None:
    statuses = validate_all_schemas()

    assert statuses
    assert all(status.valid for status in statuses), statuses


def test_schemas_have_version_property() -> None:
    for path in iter_schema_paths():
        schema = json.loads(path.read_text(encoding="utf-8"))

        assert "schema_version" in schema["properties"], path


def test_packaged_schema_mirror_matches_source_schemas() -> None:
    source_names = {path.name for path in Path("schemas").glob("*.schema.json")}
    packaged_names = {path.name for path in Path("loopforge/schema_files").glob("*.schema.json")}

    assert packaged_names == source_names
