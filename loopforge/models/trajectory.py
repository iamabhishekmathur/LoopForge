"""Compact trace trajectory model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TraceTrajectory:
    trace_id: str
    started_at: str
    runtime_manifest_id: str | None
    span_count: int
    tool_calls: list[str]
    side_effect_classes: list[str]
    error_count: int
    feedback_values: list[str]
    evidence_span_ids: list[str]
    signals: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "trajectory_id": f"trajectory_{self.trace_id}",
            "trace_id": self.trace_id,
            "started_at": self.started_at,
            "runtime_manifest_id": self.runtime_manifest_id,
            "span_count": self.span_count,
            "tool_calls": self.tool_calls,
            "side_effect_classes": self.side_effect_classes,
            "error_count": self.error_count,
            "feedback_values": self.feedback_values,
            "evidence_span_ids": self.evidence_span_ids,
            "signals": self.signals,
            "metadata": self.metadata,
        }
