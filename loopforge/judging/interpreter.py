"""Provider-agnostic trace interpretation."""

from __future__ import annotations

import json
import re
from typing import Any

from loopforge.models.observed import ObservedAgentRun, ObservedStep
from loopforge.models.trace import Span, Trace


USER_INTENT_KEYS = (
    "user_message",
    "user_query",
    "query",
    "user_input",
    "input",
    "question",
    "prompt",
    "message",
    "messages",
)
FINAL_RESPONSE_KEYS = (
    "assistant_message",
    "final_response",
    "answer",
    "response",
    "output",
    "text",
    "content",
    "message",
)
TOOLISH_TYPES = {"tool_call", "router", "retriever", "application"}


def interpret_trace(trace: Trace) -> ObservedAgentRun:
    user_intent = _extract_user_intent(trace)
    final_response = _extract_final_response(trace)
    tool_calls = _extract_tool_calls(trace.spans)
    steps = [
        ObservedStep(
            step_id=span.span_id,
            name=span.name,
            step_type=span.type,
            input_preview=_preview(span.input),
            output_preview=_preview(span.output),
            error=span.error,
            metadata={
                "side_effect_class": span.side_effect_class,
                "raw_type": span.metadata.get("raw_type"),
            },
        )
        for span in trace.spans
    ]
    available = _available_evidence(trace, user_intent, final_response, tool_calls)
    missing = _missing_evidence(available)
    return ObservedAgentRun(
        trace_id=trace.trace_id,
        started_at=trace.started_at,
        user_intent=user_intent,
        final_response=final_response,
        tool_calls=tool_calls,
        steps=steps,
        errors=[str(span.error) for span in trace.spans if span.error],
        available_evidence=available,
        missing_evidence=missing,
        judgeability_score=_judgeability_score(available),
        metadata={
            "span_count": len(trace.spans),
            "session_id": trace.session_id,
            "source_type": trace.metadata.get("source_type"),
            "source_id": trace.metadata.get("source_id"),
        },
    )


def _extract_user_intent(trace: Trace) -> str | None:
    candidates: list[Any] = [trace.inputs]
    candidates.extend(span.input for span in trace.spans)
    for candidate in candidates:
        value = _find_text(candidate, USER_INTENT_KEYS)
        if value and not _looks_like_sql_only(value):
            return value
    return None


def _extract_final_response(trace: Trace) -> str | None:
    candidates: list[Any] = [trace.outputs]
    candidates.extend(reversed([span.output for span in trace.spans]))
    for candidate in candidates:
        value = _find_text(candidate, FINAL_RESPONSE_KEYS)
        if value and not _looks_like_tabular_payload(value):
            return value
    return None


def _extract_tool_calls(spans: list[Span]) -> list[str]:
    calls = []
    for span in spans:
        if span.type in TOOLISH_TYPES:
            calls.append(span.name)
    return calls


def _available_evidence(
    trace: Trace,
    user_intent: str | None,
    final_response: str | None,
    tool_calls: list[str],
) -> list[str]:
    evidence = []
    if user_intent:
        evidence.append("user_intent")
    if final_response:
        evidence.append("final_response")
    if tool_calls:
        evidence.append("tool_calls")
    if trace.spans:
        evidence.append("execution_steps")
    if any(span.error for span in trace.spans):
        evidence.append("errors")
    if _has_sql(trace):
        evidence.append("generated_query")
    if any(_guardrail_signal(span) for span in trace.spans):
        evidence.append("guardrail_verdict")
    if trace.feedback:
        evidence.append("feedback")
    return sorted(set(evidence))


def _missing_evidence(available: list[str]) -> list[str]:
    expected = [
        "user_intent",
        "tool_calls",
        "final_response",
        "guardrail_verdict",
    ]
    return [item for item in expected if item not in available]


def _judgeability_score(available: list[str]) -> float:
    weights = {
        "user_intent": 0.24,
        "tool_calls": 0.18,
        "execution_steps": 0.12,
        "generated_query": 0.12,
        "final_response": 0.20,
        "guardrail_verdict": 0.08,
        "feedback": 0.06,
    }
    return round(min(1.0, sum(weights[item] for item in available if item in weights)), 2)


def _find_text(value: Any, keys: tuple[str, ...]) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, list):
        for item in value:
            if isinstance(item, (dict, list)):
                found = _find_text(item, keys)
                if found:
                    return found
        return None
    if isinstance(value, dict):
        for key in keys:
            if key in value:
                found = _extract_string(value[key])
                if found:
                    return found
        for item in value.values():
            if isinstance(item, (dict, list)):
                found = _find_text(item, keys)
                if found:
                    return found
    return None


def _extract_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, list):
        parts = [_extract_string(item) for item in value]
        text = "\n".join(part for part in parts if part)
        return _clean_text(text) if text else None
    if isinstance(value, dict):
        if "content" in value:
            return _extract_string(value["content"])
        if "text" in value:
            return _extract_string(value["text"])
        if "role" in value and value.get("role") == "user":
            return _extract_string(value.get("content"))
    return None


def _clean_text(value: str) -> str | None:
    text = re.sub(r"\s+", " ", value).strip()
    return text or None


def _preview(value: Any, max_chars: int = 360) -> str:
    try:
        text = json.dumps(value, sort_keys=True)
    except TypeError:
        text = str(value)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_chars:
        return text[:max_chars] + "..."
    return text


def _looks_like_sql_only(text: str) -> bool:
    lowered = text.lower().lstrip()
    return lowered.startswith(("select ", "with ", "insert ", "update ", "delete "))


def _looks_like_tabular_payload(text: str) -> bool:
    lowered = text.lower()
    return "rowscount" in lowered or ("columns" in lowered and "rows" in lowered)


def _has_sql(trace: Trace) -> bool:
    values = [trace.inputs, trace.outputs]
    values.extend(span.input for span in trace.spans)
    values.extend(span.output for span in trace.spans)
    return any("db_query" in value or "sql" in value.lower() for value in map(_preview, values))


def _guardrail_signal(span: Span) -> bool:
    lowered = f"{span.name} {span.type} {_preview(span.input)} {_preview(span.output)}".lower()
    return "guardrail" in lowered or "rail" in lowered or "policy" in lowered
