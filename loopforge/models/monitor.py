"""Monitor run model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MonitorRun:
    run_id: str
    status: str
    started_at: str
    finished_at: str | None
    window: str
    trace_path: str
    counts: dict[str, int]
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MonitorRun":
        return cls(
            run_id=str(data["run_id"]),
            status=str(data["status"]),
            started_at=str(data["started_at"]),
            finished_at=str(data["finished_at"]) if data.get("finished_at") else None,
            window=str(data["window"]),
            trace_path=str(data["trace_path"]),
            counts={str(key): int(value) for key, value in dict(data.get("counts") or {}).items()},
            error=str(data["error"]) if data.get("error") else None,
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "run_id": self.run_id,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "window": self.window,
            "trace_path": self.trace_path,
            "counts": self.counts,
            "error": self.error,
            "metadata": self.metadata,
        }
