"""Conservatively stitch partial runtime traces to nearby turn context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from loopforge.judging.interpreter import interpret_trace
from loopforge.models.observed import ObservedAgentRun
from loopforge.models.trace import Trace


STRONG_CORRELATION_KEYS = {
    "conversation_id",
    "current_turn_id",
    "message_id",
    "source_message_id",
    "thread_id",
    "turn_id",
    "workflow_run_id",
}
TEMPORAL_WINDOW_SECONDS = 180
MIN_STITCH_CONFIDENCE = 0.65


@dataclass(frozen=True)
class StitchCandidate:
    trace: Trace
    observed: ObservedAgentRun
    shared_ids: set[str]
    method: str
    confidence: float
    time_delta_seconds: float | None


def stitch_traces(traces: list[Trace]) -> list[Trace]:
    """Return traces with inherited turn context where correlation is defensible."""
    if len(traces) < 2:
        return traces
    observations = {trace.trace_id: interpret_trace(trace) for trace in traces}
    contexts = [
        trace
        for trace in traces
        if observations[trace.trace_id].user_intent or observations[trace.trace_id].final_response
    ]
    if not contexts:
        return traces

    stitched: list[Trace] = []
    for trace in traces:
        observed = observations[trace.trace_id]
        needs_user = "user_intent" in observed.missing_evidence
        needs_final = "final_response" in observed.missing_evidence
        if not (needs_user or needs_final):
            stitched.append(trace)
            continue
        candidate = _best_candidate(trace, observed, contexts, observations)
        if candidate is None:
            stitched.append(trace)
            continue
        stitched.append(_apply_candidate(trace, observed, candidate))
    return stitched


def _best_candidate(
    trace: Trace,
    observed: ObservedAgentRun,
    contexts: list[Trace],
    observations: dict[str, ObservedAgentRun],
) -> StitchCandidate | None:
    trace_ids = _correlation_ids(trace)
    best: StitchCandidate | None = None
    for candidate_trace in contexts:
        if candidate_trace.trace_id == trace.trace_id:
            continue
        candidate_observed = observations[candidate_trace.trace_id]
        if "user_intent" in observed.missing_evidence and not candidate_observed.user_intent:
            continue
        if "final_response" in observed.missing_evidence and not candidate_observed.final_response:
            continue
        candidate_ids = _correlation_ids(candidate_trace)
        shared_ids = trace_ids & candidate_ids
        score, method = _correlation_score(trace, candidate_trace, shared_ids)
        if score < MIN_STITCH_CONFIDENCE:
            continue
        delta = _time_delta_seconds(trace.started_at, candidate_trace.started_at)
        candidate = StitchCandidate(
            trace=candidate_trace,
            observed=candidate_observed,
            shared_ids=shared_ids,
            method=method,
            confidence=round(score, 2),
            time_delta_seconds=round(delta, 3) if delta is not None else None,
        )
        if _is_better_candidate(candidate, best):
            best = candidate
    return best


def _is_better_candidate(candidate: StitchCandidate, current: StitchCandidate | None) -> bool:
    if current is None:
        return True
    if candidate.confidence != current.confidence:
        return candidate.confidence > current.confidence
    if candidate.time_delta_seconds is None:
        return False
    if current.time_delta_seconds is None:
        return True
    return candidate.time_delta_seconds < current.time_delta_seconds


def _correlation_score(trace: Trace, candidate: Trace, shared_ids: set[str]) -> tuple[float, str]:
    if shared_ids:
        score = 0.88
        method = "shared_correlation_id"
    else:
        score = 0.0
        method = "unmatched"

    if trace.session_id and candidate.session_id and trace.session_id == candidate.session_id:
        delta = _time_delta_seconds(trace.started_at, candidate.started_at)
        if delta is not None and delta <= TEMPORAL_WINDOW_SECONDS:
            temporal_score = 0.7 + (0.18 * (1 - (delta / TEMPORAL_WINDOW_SECONDS)))
            if temporal_score > score:
                score = temporal_score
                method = "same_session_temporal"

    if trace.metadata.get("source_id") and trace.metadata.get("source_id") == candidate.metadata.get("source_id"):
        score += 0.03
    if trace.metadata.get("source_type") and trace.metadata.get("source_type") == candidate.metadata.get("source_type"):
        score += 0.02
    return min(score, 0.99), method


def _apply_candidate(trace: Trace, observed: ObservedAgentRun, candidate: StitchCandidate) -> Trace:
    payload = trace.to_dict()
    inputs = dict(payload.get("inputs") or {})
    outputs = dict(payload.get("outputs") or {})
    inherited: list[str] = []

    if "user_intent" in observed.missing_evidence and candidate.observed.user_intent:
        inputs["_loopforge_stitched_user_intent"] = candidate.observed.user_intent
        inherited.append("user_intent")
    if "final_response" in observed.missing_evidence and candidate.observed.final_response:
        outputs["_loopforge_stitched_final_response"] = candidate.observed.final_response
        inherited.append("final_response")

    if not inherited:
        return trace

    payload["inputs"] = inputs
    payload["outputs"] = outputs
    payload["metadata"] = {
        **(payload.get("metadata") or {}),
        "stitching": {
            "schema_version": "1",
            "status": "stitched",
            "source_trace_id": candidate.trace.trace_id,
            "method": candidate.method,
            "confidence": candidate.confidence,
            "inherited_evidence": inherited,
            "shared_correlation_ids": sorted(candidate.shared_ids),
            "time_delta_seconds": candidate.time_delta_seconds,
        },
    }
    return Trace.from_dict(payload)


def _correlation_ids(trace: Trace) -> set[str]:
    ids: set[str] = set()
    values: list[Any] = [trace.inputs, trace.outputs, trace.metadata]
    for span in trace.spans:
        values.extend([span.input, span.output, span.metadata])
    for value in values:
        ids.update(_walk_correlation_ids(value))
    return ids


def _walk_correlation_ids(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in STRONG_CORRELATION_KEYS:
                normalized = _normalize_id(item)
                if normalized:
                    found.add(f"{key}:{normalized}")
            if isinstance(item, (dict, list)):
                found.update(_walk_correlation_ids(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_walk_correlation_ids(item))
    return found


def _normalize_id(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or len(text) > 200:
        return None
    return text


def _time_delta_seconds(left: str, right: str) -> float | None:
    left_dt = _parse_datetime(left)
    right_dt = _parse_datetime(right)
    if left_dt is None or right_dt is None:
        return None
    return abs((left_dt - right_dt).total_seconds())


def _parse_datetime(value: str) -> datetime | None:
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None

