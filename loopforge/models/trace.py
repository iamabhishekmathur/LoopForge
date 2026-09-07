"""Trace domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Span:
    span_id: str
    type: str
    name: str
    started_at: str
    parent_span_id: str | None = None
    input: dict[str, Any] = field(default_factory=dict)
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    side_effect_class: str | None = None
    ended_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Span":
        for key in ("span_id", "type", "name", "started_at"):
            if not data.get(key):
                raise ValueError(f"span missing required field: {key}")
        return cls(
            span_id=str(data["span_id"]),
            type=str(data["type"]),
            name=str(data["name"]),
            started_at=str(data["started_at"]),
            parent_span_id=data.get("parent_span_id"),
            input=dict(data.get("input") or {}),
            output=dict(data.get("output") or {}),
            error=data.get("error"),
            side_effect_class=data.get("side_effect_class"),
            ended_at=data.get("ended_at"),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "type": self.type,
            "name": self.name,
            "input": self.input,
            "output": self.output,
            "error": self.error,
            "side_effect_class": self.side_effect_class,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class Trace:
    schema_version: str
    trace_id: str
    started_at: str
    inputs: dict[str, Any]
    spans: list[Span]
    session_id: str | None = None
    ended_at: str | None = None
    runtime_manifest_id: str | None = None
    source_trace_id: str | None = None
    replay_mode: str | None = None
    outputs: dict[str, Any] = field(default_factory=dict)
    feedback: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Trace":
        for key in ("schema_version", "trace_id", "started_at", "inputs", "spans"):
            if key not in data:
                raise ValueError(f"trace missing required field: {key}")
        if data["schema_version"] != "1":
            raise ValueError("unsupported trace schema_version")
        spans = [Span.from_dict(span) for span in data.get("spans") or []]
        if not spans:
            raise ValueError("trace must include at least one span")
        return cls(
            schema_version=str(data["schema_version"]),
            trace_id=str(data["trace_id"]),
            started_at=str(data["started_at"]),
            inputs=dict(data["inputs"] or {}),
            spans=spans,
            session_id=data.get("session_id"),
            ended_at=data.get("ended_at"),
            runtime_manifest_id=data.get("runtime_manifest_id"),
            source_trace_id=data.get("source_trace_id"),
            replay_mode=data.get("replay_mode"),
            outputs=dict(data.get("outputs") or {}),
            feedback=list(data.get("feedback") or []),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "runtime_manifest_id": self.runtime_manifest_id,
            "source_trace_id": self.source_trace_id,
            "replay_mode": self.replay_mode,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "feedback": self.feedback,
            "spans": [span.to_dict() for span in self.spans],
            "metadata": self.metadata,
        }
