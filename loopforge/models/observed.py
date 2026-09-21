"""Observed agent-run models derived from provider traces."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ObservedStep:
    step_id: str
    name: str
    step_type: str
    input_preview: str = ""
    output_preview: str = ""
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "name": self.name,
            "step_type": self.step_type,
            "input_preview": self.input_preview,
            "output_preview": self.output_preview,
            "error": self.error,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class ObservedAgentRun:
    trace_id: str
    started_at: str
    user_intent: str | None
    final_response: str | None
    tool_calls: list[str]
    steps: list[ObservedStep]
    errors: list[str]
    available_evidence: list[str]
    missing_evidence: list[str]
    judgeability_score: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "trace_id": self.trace_id,
            "started_at": self.started_at,
            "user_intent": self.user_intent,
            "final_response": self.final_response,
            "tool_calls": self.tool_calls,
            "steps": [step.to_dict() for step in self.steps],
            "errors": self.errors,
            "available_evidence": self.available_evidence,
            "missing_evidence": self.missing_evidence,
            "judgeability_score": self.judgeability_score,
            "metadata": self.metadata,
        }

