"""Trace connector sync state persistence."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

from loopforge.models.sync import TraceSyncState
from loopforge.models.trace import Trace
from loopforge.paths import LOCAL_DIR


def sync_state_path(root: Path, source_id: str) -> Path:
    return root / LOCAL_DIR / "connectors" / f"{source_id}-sync.json"


def read_sync_state(root: Path, source_id: str) -> TraceSyncState | None:
    path = sync_state_path(root, source_id)
    if not path.exists():
        return None
    return TraceSyncState.from_dict(json.loads(path.read_text(encoding="utf-8")))


def write_sync_state(root: Path, state: TraceSyncState) -> Path:
    path = sync_state_path(root, state.source_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return path


def update_sync_state_from_traces(
    root: Path,
    *,
    source_id: str,
    source_type: str,
    traces: list[Trace],
    cursor: str | None = None,
) -> TraceSyncState:
    high_watermark = max((trace.started_at for trace in traces), default=None)
    last_trace_id = traces[-1].trace_id if traces else None
    state = TraceSyncState(
        source_id=source_id,
        source_type=source_type,
        status="succeeded",
        synced_at=datetime.now(UTC).isoformat(),
        trace_count=len(traces),
        high_watermark_started_at=high_watermark,
        last_trace_id=last_trace_id,
        cursor=cursor,
        metadata={
            "incremental_ready": high_watermark is not None or cursor is not None,
            "empty_sync": not traces,
        },
    )
    write_sync_state(root, state)
    return state
