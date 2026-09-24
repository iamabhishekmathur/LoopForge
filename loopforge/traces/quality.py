"""Trace eligibility rules for downstream analysis."""

from __future__ import annotations

from typing import Any


def is_analysis_eligible_trace(payload: dict[str, Any]) -> bool:
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return True
    if metadata.get("source_type") != "langsmith":
        return True
    if metadata.get("record_shape") != "runs_query":
        return True
    return metadata.get("tree_fetch_complete") is True
