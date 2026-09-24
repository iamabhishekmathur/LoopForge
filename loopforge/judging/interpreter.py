"""Provider-agnostic trace interpretation."""

from __future__ import annotations

import json
import re
from typing import Any

from loopforge.models.observed import ObservedAgentRun, ObservedStep
from loopforge.models.trace import Span, Trace


USER_INTENT_KEYS = (
    "_loopforge_stitched_user_intent",
    "user_intent",
    "original_user_query",
    "verbatim_user_query",
    "user_message",
    "user_query",
    "user_question",
    "user_questions",
    "query",
    "user_input",
    "question",
    "input",
    "prompt",
    "message",
    "messages",
)
ORIGINAL_USER_INTENT_KEYS = (
    "original_user_query",
    "original_question",
    "initial_user_query",
    "initial_query",
    "original_request",
    "verbatim_user_query",
)
EXPLICIT_USER_INTENT_KEYS = (
    "_loopforge_stitched_user_intent",
    "user_intent",
    "original_user_query",
    "verbatim_user_query",
    "user_message",
    "user_query",
    "user_question",
)
FINAL_RESPONSE_KEYS = (
    "_loopforge_stitched_final_response",
    "assistant_message",
    "final_response",
    "answer",
    "response",
    "output",
    "text",
    "content",
    "message",
)
INTERACTION_RESPONSE_KEYS = ("question", "clarification_query")
EXPECTED_CONTROL_FLOW_EXCEPTIONS = {
    "GraphInterrupt",
    "Interrupt",
    "NodeInterrupt",
}
TOOLISH_TYPES = {"tool_call", "router", "retriever", "application"}


def interpret_trace(trace: Trace) -> ObservedAgentRun:
    user_intent = _extract_user_intent(trace)
    final_response = _extract_final_response(trace)
    tool_calls = _extract_tool_calls(trace.spans)
    steps = []
    runtime_errors: list[str] = []
    control_flow_events: list[dict[str, Any]] = []
    for span in trace.spans:
        event = _expected_control_flow_event(span)
        if event:
            control_flow_events.append({"step_id": span.span_id, "name": span.name, **event})
        elif span.error:
            runtime_errors.append(str(span.error))
        steps.append(
            ObservedStep(
                step_id=span.span_id,
                name=span.name,
                step_type=span.type,
                input_preview=_preview(span.input),
                output_preview=_preview(span.output),
                error=None if event else span.error,
                metadata={
                    "side_effect_class": span.side_effect_class,
                    "raw_type": span.metadata.get("raw_type"),
                    "event_semantics": event,
                    "raw_error": span.error if event else None,
                },
            )
        )
    available = _available_evidence(
        trace,
        user_intent,
        final_response,
        tool_calls,
        runtime_errors,
        control_flow_events,
    )
    missing = _missing_evidence(available)
    return ObservedAgentRun(
        trace_id=trace.trace_id,
        started_at=trace.started_at,
        user_intent=user_intent,
        final_response=final_response,
        tool_calls=tool_calls,
        steps=steps,
        errors=runtime_errors,
        available_evidence=available,
        missing_evidence=missing,
        judgeability_score=_judgeability_score(available),
        metadata={
            "span_count": len(trace.spans),
            "session_id": trace.session_id,
            "source_type": trace.metadata.get("source_type"),
            "source_id": trace.metadata.get("source_id"),
            "control_flow_events": control_flow_events,
        },
    )


def _extract_user_intent(trace: Trace) -> str | None:
    all_candidates: list[Any] = [trace.inputs, trace.outputs]
    all_candidates.extend(span.input for span in trace.spans)
    all_candidates.extend(span.output for span in trace.spans)
    for key in ORIGINAL_USER_INTENT_KEYS:
        values: list[str] = []
        for candidate in all_candidates:
            values.extend(_find_text_values(candidate, (key,)))
        selected = _select_user_intent(values)
        if selected:
            return selected

    root_explicit_texts: list[str] = []
    for candidate in (trace.inputs, trace.outputs):
        root_explicit_texts.extend(_find_text_values(candidate, EXPLICIT_USER_INTENT_KEYS))
    selected = _select_user_intent(root_explicit_texts)
    if selected:
        return selected

    candidates: list[Any] = [trace.inputs]
    candidates.extend(span.input for span in trace.spans)
    explicit_texts: list[str] = []
    for candidate in candidates:
        explicit_texts.extend(_find_text_values(candidate, EXPLICIT_USER_INTENT_KEYS))
    selected = _select_user_intent(explicit_texts)
    if selected:
        return selected
    role_texts: list[str] = []
    for candidate in candidates:
        role_texts.extend(_role_text_candidates(candidate, {"user", "human", "humanmessage"}))
    selected = _select_user_intent(role_texts)
    if selected:
        return selected
    for candidate in candidates:
        value = _find_text(candidate, USER_INTENT_KEYS)
        marked = _extract_marked_user_question(value) if value else None
        if marked and not _looks_like_sql_only(marked):
            return marked
        if value and not _looks_like_sql_only(value) and not _looks_like_internal_prompt(value):
            return value
    return None


def _extract_final_response(trace: Trace) -> str | None:
    candidates: list[Any] = [trace.outputs]
    candidates.extend(reversed([span.output for span in trace.spans]))
    final_candidates: list[str] = []
    for candidate in candidates:
        value = _find_role_text(candidate, {"assistant", "ai", "aimessage"})
        if value and not _looks_like_tabular_payload(value):
            final_candidates.append(value)
    for candidate in candidates:
        value = _find_text(candidate, FINAL_RESPONSE_KEYS)
        if value and not _looks_like_tabular_payload(value):
            final_candidates.append(value)
    interaction_candidates: list[str] = []
    for key in INTERACTION_RESPONSE_KEYS:
        interaction_candidates.extend(_find_text_values(trace.outputs, (key,)))
    interaction_response = _select_final_response(interaction_candidates)
    if interaction_response:
        final_candidates.append(interaction_response)
    return _select_final_response(final_candidates)


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
    runtime_errors: list[str],
    control_flow_events: list[dict[str, Any]],
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
    if runtime_errors:
        evidence.append("errors")
    if control_flow_events:
        evidence.append("control_flow_events")
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


def _find_text_values(value: Any, keys: tuple[str, ...]) -> list[str]:
    values: list[str] = []
    if value is None:
        return values
    if isinstance(value, list):
        for item in value:
            values.extend(_find_text_values(item, keys))
        return values
    if isinstance(value, dict):
        for key, item in value.items():
            if key in keys:
                found = _extract_string(item)
                if found:
                    values.append(found)
            if isinstance(item, (dict, list)):
                values.extend(_find_text_values(item, keys))
    return values


def _find_role_text(value: Any, roles: set[str]) -> str | None:
    candidates = _role_text_candidates(value, roles)
    return candidates[0] if candidates else None


def _role_text_candidates(value: Any, roles: set[str]) -> list[str]:
    candidates: list[str] = []
    if value is None:
        return candidates
    if isinstance(value, list):
        if len(value) >= 2 and isinstance(value[0], str) and _normalize_role(value[0]) in roles:
            found = _extract_string(value[1])
            if found:
                candidates.append(found)
        for item in value:
            candidates.extend(_role_text_candidates(item, roles))
    if isinstance(value, dict):
        role = value.get("role") or value.get("type")
        if isinstance(role, str) and _normalize_role(role) in roles:
            found = _extract_string(value.get("content") or value.get("text") or value)
            if found:
                candidates.append(found)
        message_id = value.get("id")
        if isinstance(message_id, list) and message_id:
            message_kind = _normalize_role(str(message_id[-1]))
            if message_kind in roles:
                kwargs = value.get("kwargs") if isinstance(value.get("kwargs"), dict) else {}
                found = _extract_string(kwargs.get("content") or value.get("content") or value.get("text"))
                if found:
                    candidates.append(found)
        for item in value.values():
            if isinstance(item, (dict, list)):
                candidates.extend(_role_text_candidates(item, roles))
    return candidates


def _select_user_intent(candidates: list[str]) -> str | None:
    marked: list[str] = []
    scored: list[tuple[int, str]] = []
    for candidate in candidates:
        text = _clean_text(candidate)
        if not text or _looks_like_sql_only(text):
            continue
        extracted = _extract_marked_user_question(text)
        if extracted and not _looks_like_sql_only(extracted):
            marked.append(extracted)
            continue
        if _looks_like_internal_prompt(text):
            score = -4
        else:
            score = 0
        if len(text) <= 500:
            score += 4
        elif len(text) <= 1000:
            score += 2
        else:
            score -= 3
        lowered = text.lower()
        if "?" in text:
            score += 2
        if re.match(r"^(what|how|why|when|where|which|can|could|should|show|list|find|explain|create|generate)\b", lowered):
            score += 2
        scored.append((score, text))
    if marked:
        return sorted(marked, key=len)[0]
    viable = [item for item in scored if item[0] > 0]
    if not viable:
        return None
    viable.sort(key=lambda item: (item[0], -len(item[1])), reverse=True)
    return viable[0][1]


def _select_final_response(candidates: list[str]) -> str | None:
    scored: list[tuple[int, str]] = []
    for candidate in candidates:
        text = _clean_text(candidate)
        if not text or _looks_like_tabular_payload(text):
            continue
        if _looks_like_tool_call_payload(text) or _looks_like_internal_state_payload(text):
            continue
        if _looks_like_internal_prompt(text):
            continue
        score = 0
        if not text.lstrip().startswith(("{", "[")):
            score += 5
        else:
            score += 1
        if len(text) >= 40:
            score += 2
        if len(text) > 4000:
            score -= 2
        if re.search(r"[.!?]\s", text):
            score += 2
        if any(marker in text.lower() for marker in ("summary", "result", "report", "analysis")):
            score += 1
        scored.append((score, text))
    viable = [item for item in scored if item[0] > 0]
    if not viable:
        return None
    viable.sort(key=lambda item: (item[0], -len(item[1])), reverse=True)
    return viable[0][1]


def _normalize_role(value: str) -> str:
    return value.lower().replace("_", "").replace("-", "")


def _extract_user_question(text: str) -> str:
    return _extract_marked_user_question(text) or text


def _extract_marked_user_question(text: str) -> str | None:
    patterns = [
        r"##\s*User question\s*(.+?)(?:\s*##\s|\s*###\s|\Z)",
        r"Analytical plan request:\s*(.+?)(?:\n\s*\n|\Z)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            extracted = _clean_text(match.group(1))
            if extracted:
                return extracted
    return None


def _looks_like_internal_prompt(text: str) -> bool:
    lowered = text.lower()
    markers = (
        "## behavioural layer",
        "behavioral layer",
        "global critical rules",
        "sql generation principles",
        "complete schema",
        "custom skills",
        "you are an expert",
        "system prompt",
        "developer instruction",
        "tool instructions",
        "response format",
        "sql generation plan",
        "**sql query:**",
        "### snowflake dialect rules",
        "you will be provided",
        "critical output rule",
        "output format",
    )
    return any(marker in lowered for marker in markers)


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
        tool_text = _extract_tool_use_text(value)
        if tool_text:
            return tool_text
        if "content" in value:
            return _extract_string(value["content"])
        if "text" in value:
            return _extract_string(value["text"])
        if "role" in value and value.get("role") == "user":
            return _extract_string(value.get("content"))
        for key in ("assistant_message", "final_response", "answer", "response", "summary", "reasoning", "output"):
            if key in value:
                found = _extract_string(value[key])
                if found:
                    return found
        preview = _preview(value, max_chars=1200)
        if preview and not _looks_like_tabular_payload(preview):
            return preview
    return None


def _extract_tool_use_text(value: dict[str, Any]) -> str | None:
    value_type = _normalize_role(str(value.get("type") or ""))
    if value_type not in {"tooluse", "toolcall"}:
        return None
    tool_input = value.get("input")
    if not isinstance(tool_input, dict):
        args = value.get("args")
        tool_input = args if isinstance(args, dict) else None
    if not isinstance(tool_input, dict):
        return None
    for key in ("textToSQLSummary", "narration", "summary", "answer", "response"):
        if key in tool_input:
            found = _extract_string(tool_input[key])
            if found:
                return found
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


def _looks_like_tool_call_payload(text: str) -> bool:
    lowered = text.lower()
    return (
        '"type": "tool_use"' in lowered
        or '"type": "tool_call"' in lowered
        or ('"tool_calls"' in lowered and '"args"' in lowered)
        or ('"caller"' in lowered and '"input"' in lowered)
    )


def _looks_like_internal_state_payload(text: str) -> bool:
    lowered = text.lower()
    return (
        '"goto": "__end__"' in lowered
        or '"artifact_store"' in lowered
        or '"app_context_gathered_info"' in lowered
        or '"app_generation_context"' in lowered
        or '"goto": "agentic_human"' in lowered
        or '"agentic_run_state"' in lowered
    )


def _expected_control_flow_event(span: Span) -> dict[str, Any] | None:
    if not span.error:
        return None
    first_line = str(span.error).lstrip().splitlines()[0]
    exception_name = first_line.partition("(")[0].strip().rsplit(".", 1)[-1]
    if exception_name not in EXPECTED_CONTROL_FLOW_EXCEPTIONS:
        return None
    return {
        "category": "expected_control_flow",
        "event_type": "human_interaction_pause",
        "framework_signal": exception_name,
        "confidence": 0.99,
    }


def _has_sql(trace: Trace) -> bool:
    values = [trace.inputs, trace.outputs]
    values.extend(span.input for span in trace.spans)
    values.extend(span.output for span in trace.spans)
    return any("db_query" in value or "sql" in value.lower() for value in map(_preview, values))


def _guardrail_signal(span: Span) -> bool:
    lowered = f"{span.name} {span.type} {_preview(span.input)} {_preview(span.output)}".lower()
    return "guardrail" in lowered or "rail" in lowered or "policy" in lowered
