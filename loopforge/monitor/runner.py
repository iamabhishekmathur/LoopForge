"""Scheduled monitoring on top of the shadow pipeline."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from pathlib import Path
import re
import time

from loopforge.config import (
    configured_monitor_schedule,
    configured_monitor_trace_window,
    configured_refiner_target_scope,
    configured_trace_path,
)
from loopforge.db import Store
from loopforge.models.monitor import MonitorRun
from loopforge.queue.runner import enqueue_refiner_job
from loopforge.shadow.runner import run_shadow_pipeline


SleepFn = Callable[[float], None]


def iter_monitor_runs(
    root: Path,
    window: str | None = None,
    trace_path: str | None = None,
    interval_seconds: float | None = None,
    max_runs: int | None = 1,
    sleep: SleepFn = time.sleep,
) -> Iterator[MonitorRun]:
    resolved_window = window or configured_monitor_trace_window(root)
    resolved_trace_path = trace_path if trace_path is not None else configured_trace_path(root)
    resolved_interval = (
        interval_seconds
        if interval_seconds is not None
        else parse_schedule_seconds(configured_monitor_schedule(root))
    )

    run_count = 0
    while max_runs is None or run_count < max_runs:
        run_count += 1
        yield run_monitor_once(root, resolved_window, resolved_trace_path)
        if max_runs is None or run_count < max_runs:
            sleep(resolved_interval)


def run_monitor_once(root: Path, window: str, trace_path: str | None) -> MonitorRun:
    started_at = _now()
    run_id = "MONITOR-" + started_at.replace("-", "").replace(":", "").replace(".", "")
    trace_path_label = trace_path or "configured_trace_sources"
    running = MonitorRun(
        run_id=run_id,
        status="running",
        started_at=started_at,
        finished_at=None,
        window=window,
        trace_path=trace_path_label,
        counts={},
        metadata={"mode": "scheduled_shadow"},
    )
    store = Store.for_project(root)
    try:
        store.upsert_monitor_run(running.to_dict())
    finally:
        store.close()

    try:
        result = run_shadow_pipeline(root, window, trace_path)
        queue_item = enqueue_refiner_job(
            root,
            trigger="monitor_schedule",
            trace_window=window,
            target_scope=configured_refiner_target_scope(root),
            metadata={
                "monitor_run_id": run_id,
                "trace_path": result.trace_path,
                "issue_count": result.issue_count,
            },
        )
        finished = MonitorRun(
            run_id=run_id,
            status="succeeded",
            started_at=started_at,
            finished_at=_now(),
            window=window,
            trace_path=result.trace_path,
            counts={
                "traces": result.trace_count,
                "trajectories": result.trajectory_count,
                "artifacts": result.artifact_count,
                "issues": result.issue_count,
                "evals": result.eval_count,
                "validations": result.validation_count,
                "resolutions": result.resolution_count,
            },
            metadata={
                "mode": "scheduled_shadow",
                "refiner_queue_item_id": queue_item.queue_item_id,
                "reports": [path.relative_to(root).as_posix() for path in result.report_paths],
            },
        )
    except Exception as exc:
        finished = MonitorRun(
            run_id=run_id,
            status="failed",
            started_at=started_at,
            finished_at=_now(),
            window=window,
            trace_path=trace_path_label,
            counts={},
            error=str(exc),
            metadata={"mode": "scheduled_shadow"},
        )

    store = Store.for_project(root)
    try:
        store.upsert_monitor_run(finished.to_dict())
    finally:
        store.close()
    return finished


def parse_schedule_seconds(value: str) -> float:
    stripped = value.strip().lower()
    if stripped.startswith("every "):
        stripped = stripped.removeprefix("every ").strip()
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours)", stripped)
    if match is None:
        raise ValueError(f"unsupported monitor schedule: {value}")
    amount = float(match.group(1))
    unit = match.group(2)
    if unit.startswith("s"):
        return amount
    if unit.startswith("m"):
        return amount * 60
    if unit.startswith("h"):
        return amount * 3600
    raise ValueError(f"unsupported monitor schedule: {value}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
