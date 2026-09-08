"""Trace connector sync state model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TraceSyncState:
    source_id: str
    source_type: str
    status: str
    synced_at: str
    trace_count: int
    high_watermark_started_at: str | None = None
    last_trace_id: str | None = None
    cursor: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TraceSyncState":
        return cls(
            source_id=str(data["source_id"]),
            source_type=str(data["source_type"]),
            status=str(data["status"]),
            synced_at=str(data["synced_at"]),
            trace_count=int(data.get("trace_count") or 0),
            high_watermark_started_at=str(data["high_watermark_started_at"])
            if data.get("high_watermark_started_at")
            else None,
            last_trace_id=str(data["last_trace_id"]) if data.get("last_trace_id") else None,
            cursor=str(data["cursor"]) if data.get("cursor") else None,
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "source_id": self.source_id,
            "source_type": self.source_type,
            "status": self.status,
            "synced_at": self.synced_at,
            "trace_count": self.trace_count,
            "high_watermark_started_at": self.high_watermark_started_at,
            "last_trace_id": self.last_trace_id,
            "cursor": self.cursor,
            "metadata": self.metadata,
        }
