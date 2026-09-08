"""Hosted trace adapters and provider payload normalization."""

from __future__ import annotations

from dataclasses import dataclass
import base64
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
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
        headers = {"Accept": "application/json"}
        headers.update(_auth_headers(self.source_type, self.api_key, self.settings))
        request = Request(endpoint, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=float(self.settings.get("timeout_seconds", "30"))) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise ValueError(f"{self.source_id}: failed to fetch hosted traces: {exc}") from exc

    def _endpoint(self) -> str:
        if self.settings.get("url"):
            return self.settings["url"]
        base_url = self.settings.get("base_url")
        if not base_url:
            raise ValueError(f"{self.source_id}: hosted sources require url or base_url")
        params = {
            key: value
            for key, value in {
                "project": self.settings.get("project"),
                "project_name": self.settings.get("project_name"),
                "limit": self.settings.get("limit"),
                "from": self.settings.get("from"),
                "to": self.settings.get("to"),
            }.items()
            if value
        }
        query = f"?{urlencode(params)}" if params else ""
        return base_url.rstrip("/") + _default_path(self.source_type) + query


def normalize_provider_payload(
    source_type: str,
    payload: Any,
    source_id: str,
) -> list[Trace]:
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
    span_type = _span_type(str(span.get("type") or span.get("run_type") or span.get("kind") or "application"))
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
    if lowered in {"llm", "llm_call", "generation"}:
        return "llm_call"
    if lowered in {"tool", "tool_call"}:
        return "tool_call"
    if lowered in {"retrieval", "retriever"}:
        return "retrieval"
    if lowered in {"router", "chain"}:
        return "router"
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
        "langsmith": "/runs",
        "langfuse": "/api/public/traces",
        "phoenix": "/v1/traces",
        "braintrust": "/v1/traces",
        "opentelemetry": "/v1/traces",
        "openinference": "/v1/traces",
        "http": "",
    }.get(source_type, "")
