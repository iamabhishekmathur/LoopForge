"""Async refinement queue item model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RefinerQueueItem:
    queue_item_id: str
    trigger: str
    status: str
    trace_window: str
    target_scope: str
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    budget: dict[str, int] = field(default_factory=dict)
    attempt_count: int = 0
    last_error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RefinerQueueItem":
        return cls(
            queue_item_id=str(data["queue_item_id"]),
            trigger=str(data["trigger"]),
            status=str(data["status"]),
            trace_window=str(data["trace_window"]),
            target_scope=str(data.get("target_scope") or "workflow"),
            created_at=str(data["created_at"]),
            started_at=str(data["started_at"]) if data.get("started_at") else None,
            finished_at=str(data["finished_at"]) if data.get("finished_at") else None,
            budget={str(key): int(value) for key, value in dict(data.get("budget") or {}).items()},
            attempt_count=int(data.get("attempt_count") or 0),
            last_error=str(data["last_error"]) if data.get("last_error") else None,
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "queue_item_id": self.queue_item_id,
            "trigger": self.trigger,
            "status": self.status,
            "trace_window": self.trace_window,
            "target_scope": self.target_scope,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "budget": self.budget,
            "attempt_count": self.attempt_count,
            "last_error": self.last_error,
            "metadata": self.metadata,
        }
