"""Harness artifact model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class HarnessArtifact:
    artifact_id: str
    artifact_type: str
    path: str
    confidence: float
    last_indexed_at: str
    symbol_or_anchor: str | None = None
    summary: str | None = None
    discovered_by: list[str] = field(default_factory=list)
    relationships: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HarnessArtifact":
        return cls(
            artifact_id=str(data["artifact_id"]),
            artifact_type=str(data["artifact_type"]),
            path=str(data["path"]),
            confidence=float(data["confidence"]),
            last_indexed_at=str(data["last_indexed_at"]),
            symbol_or_anchor=data.get("symbol_or_anchor"),
            summary=data.get("summary"),
            discovered_by=list(data.get("discovered_by") or []),
            relationships=list(data.get("relationships") or []),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "path": self.path,
            "symbol_or_anchor": self.symbol_or_anchor,
            "summary": self.summary,
            "confidence": self.confidence,
            "discovered_by": self.discovered_by,
            "last_indexed_at": self.last_indexed_at,
            "relationships": self.relationships,
            "metadata": self.metadata,
        }
