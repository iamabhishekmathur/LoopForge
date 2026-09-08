"""Hosted trace adapters and provider payload normalization."""

from __future__ import annotations

from dataclasses import dataclass
import base64
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from loopforge.adapters.base import TraceAdapter
from loopforge.models.trace import Trace


SUPPORTED_HOSTED_TYPES = {
    "langsmith",
    "langfuse",
    "phoenix",
    "braintrust",
    "opentelemetry",
    "openinference",
    "http",
}


@dataclass(frozen=True)
class HostedTraceAdapter(TraceAdapter):
    source_id: str
    source_type: str
    settings: dict[str, str]
    api_key: str | None = None
    since: str | None = None
    cursor: str | None = None
    id: str = "hosted"

    def read(self, root: Path) -> list[Trace]:
        if self.settings.get("fixture_path"):
            return self._read_fixture(root / self.settings["fixture_path"])
        payload = self._fetch_payload()
        return normalize_provider_payload(self.source_type, payload, self.source_id)

    def _read_fixture(self, path: Path) -> list[Trace]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"{path}: invalid hosted trace fixture: {exc}") from exc
        return normalize_provider_payload(self.source_type, payload, self.source_id)

    def _fetch_payload(self) -> Any:
        endpoint = self._endpoint()
        payload = self._fetch_page(endpoint)
        if not self._should_paginate():
            return payload

        combined = payload
        seen_cursors: set[str] = set()
        next_cursor = _next_cursor(payload)
        max_pages = int(self.settings.get("max_pages", "5"))
        page_count = 1
        while next_cursor and next_cursor not in seen_cursors and page_count < max_pages:
            seen_cursors.add(next_cursor)
            page = self._fetch_page(self._endpoint(cursor_override=next_cursor), cursor_override=next_cursor)
            combined = _merge_payloads(combined, page)
            next_cursor = _next_cursor(page)
            page_count += 1
        return combined

    def _fetch_page(self, endpoint: str, cursor_override: str | None = None) -> Any:
        headers = {"Accept": "application/json"}
        headers.update(_auth_headers(self.source_type, self.api_key, self.settings))
        body = self._request_body(cursor_override)
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(endpoint, data=data, headers=headers, method=self._request_method())
        try:
            with urlopen(request, timeout=float(self.settings.get("timeout_seconds", "30"))) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise ValueError(f"{self.source_id}: failed to fetch hosted traces: {exc}") from exc

    def _endpoint(self, cursor_override: str | None = None) -> str:
        if self.settings.get("url"):
            params = self._query_params(cursor_override)
            if cursor_override and "cursor" not in params:
                params["cursor"] = cursor_override
            return _append_query(self.settings["url"], params)
        base_url = self.settings.get("base_url")
        if not base_url:
            raise ValueError(f"{self.source_id}: hosted sources require url or base_url")
        path = self.settings.get("path") or _default_path(self.source_type)
        return _append_query(base_url.rstrip("/") + path, self._query_params(cursor_override))

    def _request_method(self) -> str:
        method = self.settings.get("method")
        if method:
            return method.upper()
        if self.source_type == "langsmith":
            return "POST"
        return "GET"

    def _request_body(self, cursor_override: str | None = None) -> dict[str, Any] | None:
        if self._request_method() != "POST":
            return None
        if self.settings.get("body"):
            try:
                body = json.loads(self.settings["body"])
            except json.JSONDecodeError as exc:
                raise ValueError(f"{self.source_id}: body must be valid JSON: {exc}") from exc
            if not isinstance(body, dict):
                raise ValueError(f"{self.source_id}: body must be a JSON object")
            return body
        if self.source_type != "langsmith":
            return {}
        body = {
            key: value
            for key, value in {
                "project_name": self.settings.get("project_name") or self.settings.get("project"),
                "project_id": self.settings.get("project_id"),
                "limit": _int_or_none(self.settings.get("limit")),
                "start_time_after": self.settings.get("since") or self.since,
                "end_time_before": self.settings.get("to"),
                "cursor": cursor_override or self.settings.get("cursor") or self.cursor,
                "filter": self.settings.get("filter"),
            }.items()
            if value is not None
        }
        return body

    def _query_params(self, cursor_override: str | None = None) -> dict[str, str]:
        cursor = cursor_override or self.settings.get("cursor") or self.cursor
        if self.source_type == "langsmith" and self._request_method() == "POST":
            return {}
        if self.source_type == "langfuse":
            return {
                key: value
                for key, value in {
                    "name": self.settings.get("name"),
                    "userId": self.settings.get("user_id"),
                    "sessionId": self.settings.get("session_id"),
                    "limit": self.settings.get("limit"),
                    "fromStartTime": self.settings.get("fromStartTime")
                    or self.settings.get("from")
                    or self.settings.get("since")
                    or self.since,
                    "toStartTime": self.settings.get("toStartTime") or self.settings.get("to"),
                    "cursor": cursor,
                    "fields": self.settings.get("fields") or "core,basic,io,metadata,model,trace_context",
                }.items()
                if value
            }
        return {
            key: value
            for key, value in {
                "project": self.settings.get("project"),
                "project_name": self.settings.get("project_name"),
                "limit": self.settings.get("limit"),
                "from": self.settings.get("from"),
                "to": self.settings.get("to"),
                "since": self.settings.get("since") or self.since,
                "cursor": cursor,
            }.items()
            if value
        }

    def _should_paginate(self) -> bool:
        return self.settings.get("pagination") == "cursor" or self.settings.get("paginate") == "true"


def normalize_provider_payload(
    source_type: str,
    payload: Any,
    source_id: str,
) -> list[Trace]:
    if source_type == "langfuse" and _is_langfuse_observation_payload(payload):
        return _normalize_langfuse_observations(payload, source_id)
    if source_type in {"opentelemetry", "openinference"} and _is_otel_payload(payload):
        return _normalize_otel_payload(source_type, payload, source_id)
    records = _extract_records(payload)
    traces = []
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            continue
        if record.get("schema_version") == "1" and record.get("spans"):
            trace_payload = dict(record)
            trace_payload.setdefault("metadata", {})
            trace_payload["metadata"] = {
                **dict(trace_payload.get("metadata") or {}),
                "source_id": source_id,
                "source_type": source_type,
            }
            traces.append(Trace.from_dict(trace_payload))
            continue
        traces.append(_normalize_record(source_type, source_id, index, record))
    return traces


def _normalize_record(
    source_type: str,
    source_id: str,
    index: int,
    record: dict[str, Any],
) -> Trace:
    source_trace_id = str(
        record.get("trace_id")
        or record.get("id")
        or record.get("run_id")
        or record.get("span_id")
        or f"{source_id}-{index}"
    )
    started_at = str(
        record.get("started_at")
        or record.get("start_time")
        or record.get("timestamp")
        or record.get("created_at")
        or "1970-01-01T00:00:00Z"
    )
    spans = _record_spans(source_type, source_trace_id, started_at, record)
    payload = {
        "schema_version": "1",
        "trace_id": f"{source_id}:{source_trace_id}",
        "source_trace_id": source_trace_id,
        "session_id": record.get("session_id"),
        "started_at": started_at,
        "ended_at": record.get("ended_at") or record.get("end_time"),
        "runtime_manifest_id": record.get("runtime_manifest_id"),
        "replay_mode": "none",
        "inputs": _object(record.get("inputs") or record.get("input")),
        "outputs": _object(record.get("outputs") or record.get("output")),
        "feedback": _feedback(record),
        "spans": spans,
        "metadata": {
            "source_id": source_id,
            "source_type": source_type,
            "raw_keys": sorted(record.keys()),
        },
    }
    return Trace.from_dict(payload)


def _record_spans(
    source_type: str,
    source_trace_id: str,
    started_at: str,
    record: dict[str, Any],
) -> list[dict[str, Any]]:
    raw_spans = (
        record.get("spans")
        or record.get("runs")
        or record.get("child_runs")
        or record.get("observations")
        or record.get("events")
        or []
    )
    spans = []
    if isinstance(raw_spans, list):
        for index, span in enumerate(raw_spans, start=1):
            if isinstance(span, dict):
                spans.append(_normalize_span(source_type, source_trace_id, index, span))
    if not spans:
        spans.append(_normalize_span(source_type, source_trace_id, 1, record))
    return spans


def _normalize_span(
    source_type: str,
    source_trace_id: str,
    index: int,
    span: dict[str, Any],
) -> dict[str, Any]:
    span_id = str(span.get("span_id") or span.get("id") or span.get("run_id") or f"{source_trace_id}-{index}")
    raw_type = span.get("type") or span.get("run_type") or span.get("kind") or span.get("span_kind")
    span_type = _span_type(str(raw_type or "application"))
    return {
        "span_id": span_id,
        "parent_span_id": span.get("parent_span_id") or span.get("parent_id"),
        "type": span_type,
        "name": str(span.get("name") or span.get("operation") or source_type),
        "input": _object(span.get("input") or span.get("inputs")),
        "output": _object(span.get("output") or span.get("outputs")),
        "error": span.get("error") or span.get("exception"),
        "side_effect_class": span.get("side_effect_class"),
        "started_at": str(
            span.get("started_at")
            or span.get("start_time")
            or span.get("timestamp")
            or span.get("created_at")
            or "1970-01-01T00:00:00Z"
        ),
        "ended_at": span.get("ended_at") or span.get("end_time"),
        "metadata": {
            "source_type": source_type,
            "raw_type": span.get("type") or span.get("run_type") or span.get("kind"),
        },
    }


def _normalize_langfuse_observations(payload: Any, source_id: str) -> list[Trace]:
    observations = _extract_records(payload)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for observation in observations:
        if not isinstance(observation, dict):
            continue
        trace_id = observation.get("traceId") or observation.get("trace_id")
        if trace_id:
            grouped.setdefault(str(trace_id), []).append(observation)

    traces: list[Trace] = []
    for trace_id, group in grouped.items():
        sorted_group = sorted(group, key=lambda item: _started_at(item))
        root_observation = _first_root_observation(sorted_group)
        spans = [
            _normalize_langfuse_observation_span(trace_id, index, observation)
            for index, observation in enumerate(sorted_group, start=1)
        ]
        trace_payload = {
            "schema_version": "1",
            "trace_id": f"{source_id}:{trace_id}",
            "source_trace_id": trace_id,
            "session_id": root_observation.get("sessionId") or root_observation.get("session_id"),
            "started_at": _started_at(sorted_group[0]),
            "ended_at": _ended_at(sorted_group[-1]),
            "runtime_manifest_id": None,
            "replay_mode": "none",
            "inputs": _object(root_observation.get("input")),
            "outputs": _object(root_observation.get("output")),
            "feedback": _feedback(root_observation),
            "spans": spans,
            "metadata": {
                "source_id": source_id,
                "source_type": "langfuse",
                "record_shape": "v2_observations",
            },
        }
        traces.append(Trace.from_dict(trace_payload))
    return traces


def _normalize_langfuse_observation_span(
    source_trace_id: str,
    index: int,
    observation: dict[str, Any],
) -> dict[str, Any]:
    raw_type = observation.get("type") or observation.get("kind")
    return {
        "span_id": str(observation.get("id") or f"{source_trace_id}-{index}"),
        "parent_span_id": observation.get("parentObservationId") or observation.get("parent_observation_id"),
        "type": _span_type(str(raw_type or "application")),
        "name": str(observation.get("name") or "langfuse_observation"),
        "input": _object(observation.get("input")),
        "output": _object(observation.get("output")),
        "error": observation.get("error") or observation.get("statusMessage"),
        "side_effect_class": _metadata_value(observation, "side_effect_class"),
        "started_at": _started_at(observation),
        "ended_at": _ended_at(observation),
        "metadata": {
            "source_type": "langfuse",
            "raw_type": raw_type,
            "level": observation.get("level"),
        },
    }


def _normalize_otel_payload(source_type: str, payload: dict[str, Any], source_id: str) -> list[Trace]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for span in _flatten_otel_spans(payload):
        trace_id = span.get("trace_id") or span.get("traceId")
        if trace_id:
            grouped.setdefault(str(trace_id), []).append(span)

    traces: list[Trace] = []
    for trace_id, spans in grouped.items():
        sorted_spans = sorted(spans, key=lambda item: _started_at(item))
        root_span = sorted_spans[0]
        normalized_spans = [
            _normalize_otel_span(source_type, trace_id, index, span)
            for index, span in enumerate(sorted_spans, start=1)
        ]
        trace_payload = {
            "schema_version": "1",
            "trace_id": f"{source_id}:{trace_id}",
            "source_trace_id": trace_id,
            "session_id": _attrs(root_span).get("session.id") or _attrs(root_span).get("session_id"),
            "started_at": _started_at(root_span),
            "ended_at": _ended_at(sorted_spans[-1]),
            "runtime_manifest_id": _attrs(root_span).get("loopforge.runtime_manifest_id"),
            "replay_mode": "none",
            "inputs": _object(_parse_jsonish(_attrs(root_span).get("input.value") or _attrs(root_span).get("openinference.input.value"))),
            "outputs": _object(_parse_jsonish(_attrs(root_span).get("output.value") or _attrs(root_span).get("openinference.output.value"))),
            "feedback": [],
            "spans": normalized_spans,
            "metadata": {
                "source_id": source_id,
                "source_type": source_type,
                "record_shape": "otel_resource_spans",
            },
        }
        traces.append(Trace.from_dict(trace_payload))
    return traces


def _normalize_otel_span(
    source_type: str,
    source_trace_id: str,
    index: int,
    span: dict[str, Any],
) -> dict[str, Any]:
    attributes = _attrs(span)
    raw_type = (
        attributes.get("openinference.span.kind")
        or attributes.get("gen_ai.operation.name")
        or span.get("type")
        or span.get("kind")
        or "application"
    )
    status = span.get("status") if isinstance(span.get("status"), dict) else {}
    return {
        "span_id": str(span.get("span_id") or span.get("spanId") or f"{source_trace_id}-{index}"),
        "parent_span_id": span.get("parent_span_id") or span.get("parentSpanId"),
        "type": _span_type(str(raw_type)),
        "name": str(span.get("name") or attributes.get("tool.name") or source_type),
        "input": _object(_parse_jsonish(attributes.get("input.value") or attributes.get("openinference.input.value"))),
        "output": _object(_parse_jsonish(attributes.get("output.value") or attributes.get("openinference.output.value"))),
        "error": span.get("error") or status.get("message"),
        "side_effect_class": attributes.get("loopforge.side_effect_class") or attributes.get("side_effect_class"),
        "started_at": _started_at(span),
        "ended_at": _ended_at(span),
        "metadata": {
            "source_type": source_type,
            "raw_type": raw_type,
            "otel_kind": span.get("kind"),
        },
    }


def _extract_records(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("traces", "runs", "data", "results", "observations", "spans", "resourceSpans"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return [payload]


def _flatten_otel_spans(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    for resource_span in payload.get("resourceSpans") or []:
        if not isinstance(resource_span, dict):
            continue
        resource_attributes = _attrs(resource_span.get("resource") or {})
        if isinstance(resource_span.get("spans"), list):
            for span in resource_span["spans"]:
                if isinstance(span, dict):
                    spans.append(_with_resource_context(span, resource_span, resource_attributes))
        for scope_span in resource_span.get("scopeSpans") or []:
            if not isinstance(scope_span, dict):
                continue
            for span in scope_span.get("spans") or []:
                if isinstance(span, dict):
                    spans.append(_with_resource_context(span, resource_span, resource_attributes))
    return spans


def _with_resource_context(
    span: dict[str, Any],
    resource_span: dict[str, Any],
    resource_attributes: dict[str, Any],
) -> dict[str, Any]:
    copied = dict(span)
    copied.setdefault("trace_id", resource_span.get("trace_id") or resource_span.get("traceId"))
    copied.setdefault("started_at", resource_span.get("started_at"))
    attributes = {**resource_attributes, **_attrs(span)}
    copied["attributes"] = attributes
    return copied


def _feedback(record: dict[str, Any]) -> list[dict[str, Any]]:
    feedback = record.get("feedback")
    if isinstance(feedback, list):
        normalized = []
        for item in feedback:
            if isinstance(item, dict) and "type" in item and "value" in item:
                normalized.append(item)
        return normalized
    if record.get("score") is not None:
        return [{"type": "score", "value": record["score"]}]
    return []


def _object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    return {"value": value}


def _span_type(value: str) -> str:
    lowered = value.lower()
    if lowered in {"llm", "llm_call", "generation", "chat", "completion"}:
        return "llm_call"
    if lowered in {"tool", "tool_call", "function"}:
        return "tool_call"
    if lowered in {"retrieval", "retriever"}:
        return "retrieval"
    if lowered in {"router", "chain"}:
        return "router"
    if lowered in {"human_approval", "approval", "confirmation"}:
        return "human_approval"
    if "error" in lowered:
        return "error"
    return "application"


def _auth_headers(source_type: str, api_key: str | None, settings: dict[str, str]) -> dict[str, str]:
    if not api_key:
        return {}
    if source_type == "langfuse" and settings.get("secret_key"):
        token = base64.b64encode(f"{api_key}:{settings['secret_key']}".encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {token}"}
    return {"Authorization": f"Bearer {api_key}"}


def _default_path(source_type: str) -> str:
    return {
        "langsmith": "/runs/query",
        "langfuse": "/api/public/v2/observations",
        "phoenix": "/v1/traces",
        "braintrust": "/v1/traces",
        "opentelemetry": "/v1/traces",
        "openinference": "/v1/traces",
        "http": "",
    }.get(source_type, "")


def _append_query(url: str, params: dict[str, str]) -> str:
    if not params:
        return url
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(params)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _merge_payloads(left: Any, right: Any) -> Any:
    if isinstance(left, list) and isinstance(right, list):
        return [*left, *right]
    if not isinstance(left, dict) or not isinstance(right, dict):
        return left
    merged = dict(left)
    for key in ("traces", "runs", "data", "results", "observations", "spans", "resourceSpans"):
        if isinstance(left.get(key), list) and isinstance(right.get(key), list):
            merged[key] = [*left[key], *right[key]]
            return merged
    return merged


def _next_cursor(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    candidates = [
        payload.get("next_cursor"),
        payload.get("nextCursor"),
        payload.get("cursor"),
    ]
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    candidates.extend([meta.get("nextCursor"), meta.get("next_cursor"), meta.get("cursor")])
    pagination = payload.get("pagination") if isinstance(payload.get("pagination"), dict) else {}
    candidates.extend(
        [
            pagination.get("nextCursor"),
            pagination.get("next_cursor"),
            pagination.get("cursor"),
        ]
    )
    for candidate in candidates:
        if candidate:
            return str(candidate)
    return None


def _is_langfuse_observation_payload(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    records = payload.get("data") or payload.get("observations")
    if not isinstance(records, list) or not records:
        return False
    return any(isinstance(record, dict) and (record.get("traceId") or record.get("trace_id")) for record in records)


def _is_otel_payload(payload: Any) -> bool:
    return isinstance(payload, dict) and isinstance(payload.get("resourceSpans"), list)


def _attrs(item: dict[str, Any]) -> dict[str, Any]:
    attributes = item.get("attributes")
    if isinstance(attributes, dict):
        return attributes
    if isinstance(attributes, list):
        parsed: dict[str, Any] = {}
        for attribute in attributes:
            if not isinstance(attribute, dict) or "key" not in attribute:
                continue
            parsed[str(attribute["key"])] = _otel_value(attribute.get("value"))
        return parsed
    return {}


def _otel_value(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    for key in (
        "stringValue",
        "intValue",
        "doubleValue",
        "boolValue",
        "bytesValue",
    ):
        if key in value:
            return value[key]
    if "arrayValue" in value:
        values = value["arrayValue"].get("values") if isinstance(value["arrayValue"], dict) else []
        return [_otel_value(item) for item in values or []]
    if "kvlistValue" in value:
        values = value["kvlistValue"].get("values") if isinstance(value["kvlistValue"], dict) else []
        return {str(item.get("key")): _otel_value(item.get("value")) for item in values or [] if isinstance(item, dict)}
    return value


def _started_at(item: dict[str, Any]) -> str:
    return str(
        item.get("started_at")
        or item.get("start_time")
        or item.get("startTime")
        or _nanos_to_iso(item.get("startTimeUnixNano"))
        or item.get("timestamp")
        or item.get("created_at")
        or "1970-01-01T00:00:00Z"
    )


def _ended_at(item: dict[str, Any]) -> str | None:
    value = (
        item.get("ended_at")
        or item.get("end_time")
        or item.get("endTime")
        or _nanos_to_iso(item.get("endTimeUnixNano"))
    )
    return str(value) if value else None


def _nanos_to_iso(value: Any) -> str | None:
    if value is None:
        return None
    try:
        nanos = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(nanos / 1_000_000_000, UTC).isoformat().replace("+00:00", "Z")


def _first_root_observation(observations: list[dict[str, Any]]) -> dict[str, Any]:
    for observation in observations:
        if not (observation.get("parentObservationId") or observation.get("parent_observation_id")):
            return observation
    return observations[0]


def _metadata_value(record: dict[str, Any], key: str) -> Any:
    metadata = record.get("metadata")
    if isinstance(metadata, dict):
        return metadata.get(key)
    return None


def _parse_jsonish(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _int_or_none(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None
