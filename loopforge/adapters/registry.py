"""Trace connector registry and config parsing."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any

from loopforge.adapters.hosted import HostedTraceAdapter, SUPPORTED_HOSTED_TYPES
from loopforge.adapters.jsonl import JsonlTraceAdapter
from loopforge.models.trace import Trace
from loopforge.paths import PROJECT_CONFIG


HOSTED_CONNECTORS = {
    "langsmith": "LANGSMITH_API_KEY",
    "opentelemetry": None,
    "openinference": None,
    "langfuse": "LANGFUSE_PUBLIC_KEY",
    "phoenix": None,
    "braintrust": "BRAINTRUST_API_KEY",
    "http": None,
    "s3": None,
    "gcs": None,
}


@dataclass(frozen=True)
class TraceSourceConfig:
    source_id: str
    source_type: str
    settings: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TraceConnectorStatus:
    source_id: str
    source_type: str
    status: str
    message: str
    required_env: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "status": self.status,
            "message": self.message,
            "required_env": self.required_env,
        }


def configured_trace_sources(root: Path) -> list[TraceSourceConfig]:
    config_path = root / PROJECT_CONFIG
    if not config_path.exists():
        return [TraceSourceConfig("local-jsonl", "jsonl", {"path": "traces/*.jsonl"})]

    sources: list[TraceSourceConfig] = []
    in_traces = False
    in_sources = False
    current: dict[str, str] | None = None

    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if stripped == "traces:":
            in_traces = True
            continue
        if in_traces and raw_line and not raw_line.startswith(" "):
            if current:
                sources.append(_source_from_mapping(current, len(sources)))
            in_traces = False
            in_sources = False
            current = None
        if not in_traces:
            continue
        if stripped == "sources:":
            in_sources = True
            continue
        if not in_sources:
            continue
        if stripped.startswith("- "):
            if current:
                sources.append(_source_from_mapping(current, len(sources)))
            current = {}
            item = stripped[2:].strip()
            if item:
                _apply_key_value(current, item)
            continue
        if current is not None and ":" in stripped:
            _apply_key_value(current, stripped)

    if current:
        sources.append(_source_from_mapping(current, len(sources)))
    return sources or [TraceSourceConfig("local-jsonl", "jsonl", {"path": "traces/*.jsonl"})]


def connector_statuses(root: Path) -> list[TraceConnectorStatus]:
    return [connector_status(source) for source in configured_trace_sources(root)]


def connector_status(source: TraceSourceConfig) -> TraceConnectorStatus:
    if source.source_type == "jsonl":
        path = source.settings.get("path")
        if not path:
            return TraceConnectorStatus(
                source.source_id,
                source.source_type,
                "invalid",
                "jsonl sources require a path",
            )
        return TraceConnectorStatus(
            source.source_id,
            source.source_type,
            "ready",
            f"reads local JSONL traces from {path}",
        )

    if source.source_type in HOSTED_CONNECTORS:
        if source.settings.get("fixture_path"):
            return TraceConnectorStatus(
                source.source_id,
                source.source_type,
                "ready",
                f"reads recorded provider fixture from {source.settings['fixture_path']}",
            )
        if source.source_type in SUPPORTED_HOSTED_TYPES and (
            source.settings.get("url") or source.settings.get("base_url")
        ):
            required_env = HOSTED_CONNECTORS[source.source_type]
            if required_env and not _credential_value(source, required_env):
                return TraceConnectorStatus(
                    source.source_id,
                    source.source_type,
                    "needs_credentials",
                    f"set {required_env} before enabling hosted ingestion",
                    required_env,
                )
            return TraceConnectorStatus(
                source.source_id,
                source.source_type,
                "ready",
                "fetches hosted trace payloads over HTTP",
                required_env,
            )
        required_env = HOSTED_CONNECTORS[source.source_type]
        if required_env and not os.environ.get(required_env):
            return TraceConnectorStatus(
                source.source_id,
                source.source_type,
                "needs_credentials",
                f"set {required_env} before enabling hosted ingestion",
                required_env,
            )
        return TraceConnectorStatus(
            source.source_id,
            source.source_type,
            "setup_only",
            "connector is recognized but live ingestion is not implemented yet",
            required_env,
        )

    return TraceConnectorStatus(
        source.source_id,
        source.source_type,
        "unsupported",
        "unknown trace source type",
    )


def read_traces(root: Path, path_override: str | None = None) -> tuple[str, list[Trace]]:
    if path_override:
        return path_override, JsonlTraceAdapter(path_override).read(root)

    traces: list[Trace] = []
    source_ids: list[str] = []
    unsupported: list[TraceConnectorStatus] = []
    for source in configured_trace_sources(root):
        if source.source_type == "jsonl":
            path = source.settings.get("path")
            if not path:
                unsupported.append(connector_status(source))
                continue
            traces.extend(JsonlTraceAdapter(path).read(root))
            source_ids.append(source.source_id)
        else:
            status = connector_status(source)
            if status.status == "ready" and source.source_type in SUPPORTED_HOSTED_TYPES:
                traces.extend(
                    HostedTraceAdapter(
                        source.source_id,
                        source.source_type,
                        source.settings,
                        _credential_value(source, status.required_env),
                    ).read(root)
                )
                source_ids.append(source.source_id)
            else:
                unsupported.append(status)

    if traces:
        return ",".join(source_ids), traces
    if unsupported:
        details = "; ".join(f"{item.source_id}: {item.message}" for item in unsupported)
        raise ValueError(f"no readable trace sources: {details}")
    raise ValueError("no readable trace sources configured")


def _source_from_mapping(data: dict[str, str], index: int) -> TraceSourceConfig:
    source_type = data.get("type", "jsonl").lower()
    source_id = data.get("id") or f"{source_type}-{index + 1}"
    settings = {key: value for key, value in data.items() if key not in {"id", "type"}}
    return TraceSourceConfig(source_id, source_type, settings)


def _apply_key_value(target: dict[str, str], item: str) -> None:
    key, value = item.split(":", 1)
    target[key.strip()] = value.strip().strip("\"'")


def _credential_value(source: TraceSourceConfig, env_name: str | None) -> str | None:
    if source.settings.get("api_key"):
        return source.settings["api_key"]
    if env_name:
        return os.environ.get(env_name)
    return None
