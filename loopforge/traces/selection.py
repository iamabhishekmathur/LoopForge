"""Build canonical user-facing judge cases from provider trace roots."""

from __future__ import annotations

from dataclasses import dataclass

from loopforge.judging.interpreter import interpret_trace
from loopforge.models.trace import Trace
from loopforge.traces.stitcher import stitch_traces


@dataclass(frozen=True)
class JudgeTraceSelection:
    cases: list[Trace]
    auxiliary_trace_ids: list[str]
    excluded_trace_ids: list[str]


def select_judge_cases(traces: list[Trace]) -> JudgeTraceSelection:
    """Attach correlated tool roots to user-facing cases instead of judging them alone."""

    if not traces:
        return JudgeTraceSelection([], [], [])

    originals = {trace.trace_id: trace for trace in traces}
    original_observations = {
        trace.trace_id: interpret_trace(trace) for trace in traces
    }
    enriched = {trace.trace_id: trace for trace in stitch_traces(traces)}
    attachments: dict[str, list[Trace]] = {}
    pending_attachments: dict[str, str] = {}
    auxiliary_ids: list[str] = []
    excluded_ids: list[str] = []
    canonical_ids: list[str] = []

    for trace in traces:
        observed = original_observations[trace.trace_id]
        enriched_trace = enriched[trace.trace_id]
        stitching = enriched_trace.metadata.get("stitching")
        source_trace_id = (
            str(stitching.get("source_trace_id"))
            if isinstance(stitching, dict) and stitching.get("source_trace_id")
            else None
        )

        # A trace that borrowed its terminal response is an auxiliary execution,
        # not a second user turn. Preserve all of its spans on the source case.
        inherited = (
            set(str(item) for item in stitching.get("inherited_evidence") or [])
            if isinstance(stitching, dict)
            else set()
        )
        if source_trace_id and "final_response" in inherited:
            pending_attachments[trace.trace_id] = source_trace_id
            continue

        if observed.user_intent or observed.final_response:
            canonical_ids.append(trace.trace_id)
            continue

        if trace.metadata.get("source_type") == "langsmith":
            excluded_ids.append(trace.trace_id)
        else:
            canonical_ids.append(trace.trace_id)

    canonical_id_set = set(canonical_ids)
    for trace_id, source_trace_id in pending_attachments.items():
        target_id = _ultimate_source(source_trace_id, pending_attachments)
        if target_id in canonical_id_set:
            auxiliary_ids.append(trace_id)
            attachments.setdefault(target_id, []).append(originals[trace_id])
        else:
            excluded_ids.append(trace_id)

    cases = [
        _attach_auxiliary_traces(enriched[trace_id], attachments.get(trace_id, []))
        for trace_id in canonical_ids
    ]
    return JudgeTraceSelection(
        cases=cases,
        auxiliary_trace_ids=sorted(auxiliary_ids),
        excluded_trace_ids=sorted(excluded_ids),
    )


def _ultimate_source(source_trace_id: str, pending: dict[str, str]) -> str | None:
    current = source_trace_id
    seen: set[str] = set()
    while current in pending:
        if current in seen:
            return None
        seen.add(current)
        current = pending[current]
    return current


def _attach_auxiliary_traces(case: Trace, auxiliary: list[Trace]) -> Trace:
    if not auxiliary:
        return case
    payload = case.to_dict()
    spans = list(payload.get("spans") or [])
    seen_span_ids = {str(span.get("span_id")) for span in spans}
    for trace in auxiliary:
        for span in trace.to_dict().get("spans") or []:
            span_id = str(span.get("span_id"))
            if span_id in seen_span_ids:
                continue
            spans.append(span)
            seen_span_ids.add(span_id)
    payload["spans"] = spans
    payload["metadata"] = {
        **(payload.get("metadata") or {}),
        "judge_case": {
            "schema_version": "1",
            "role": "canonical_user_turn",
            "attached_auxiliary_trace_ids": sorted(trace.trace_id for trace in auxiliary),
            "attached_auxiliary_span_count": sum(len(trace.spans) for trace in auxiliary),
        },
    }
    return Trace.from_dict(payload)
