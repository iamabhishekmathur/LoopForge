"""Build compact trajectory summaries from full traces."""

from __future__ import annotations

from loopforge.models.trace import Trace
from loopforge.models.trajectory import TraceTrajectory


SIDE_EFFECT_SIGNALS = {
    "write": "side_effect_write",
    "money_movement": "side_effect_money_movement",
    "external_message": "side_effect_external_message",
    "destructive": "side_effect_destructive",
    "unknown": "side_effect_unknown",
}


def build_trajectory(trace: Trace) -> TraceTrajectory:
    tool_spans = [span for span in trace.spans if span.type == "tool_call"]
    side_effect_classes = [
        span.side_effect_class
        for span in tool_spans
        if span.side_effect_class is not None
    ]
    evidence_span_ids = [
        span.span_id
        for span in trace.spans
        if span.error or span.side_effect_class in SIDE_EFFECT_SIGNALS
    ]
    feedback_values = [str(item.get("value")) for item in trace.feedback if "value" in item]
    signals = []

    for side_effect_class in sorted(set(side_effect_classes)):
        signal = SIDE_EFFECT_SIGNALS.get(side_effect_class)
        if signal:
            signals.append(signal)

    if any(span.error for span in trace.spans):
        signals.append("span_error")
    if any(value.lower() in {"negative", "thumbs_down", "false"} for value in feedback_values):
        signals.append("negative_feedback")
    if len(tool_spans) >= 3 and len({span.name for span in tool_spans}) == 1:
        signals.append("repeated_tool_loop")

    return TraceTrajectory(
        trace_id=trace.trace_id,
        started_at=trace.started_at,
        runtime_manifest_id=trace.runtime_manifest_id,
        span_count=len(trace.spans),
        tool_calls=[span.name for span in tool_spans],
        side_effect_classes=side_effect_classes,
        error_count=sum(1 for span in trace.spans if span.error),
        feedback_values=feedback_values,
        evidence_span_ids=evidence_span_ids,
        signals=signals,
        metadata={
            "session_id": trace.session_id,
            "model": trace.metadata.get("model"),
            "environment": trace.metadata.get("environment"),
        },
    )
