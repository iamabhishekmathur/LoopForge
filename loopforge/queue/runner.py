"""Repository-local async refiner queue helpers."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from loopforge.db import Store
from loopforge.models.queue import RefinerQueueItem


DEFAULT_REFINER_BUDGET = {
    "max_wall_time_seconds": 300,
    "max_model_calls": 12,
    "max_tokens": 60000,
    "max_candidate_operations": 5,
}


def enqueue_refiner_job(
    root: Path,
    *,
    trigger: str,
    trace_window: str,
    target_scope: str = "workflow",
    metadata: dict[str, object] | None = None,
) -> RefinerQueueItem:
    created_at = _now()
    queue_item = RefinerQueueItem(
        queue_item_id="QUEUE-" + created_at.replace("-", "").replace(":", "").replace(".", ""),
        trigger=trigger,
        status="queued",
        trace_window=trace_window,
        target_scope=target_scope,
        created_at=created_at,
        budget=DEFAULT_REFINER_BUDGET,
        metadata=dict(metadata or {}),
    )
    store = Store.for_project(root)
    try:
        store.upsert_refiner_queue_item(queue_item.to_dict())
    finally:
        store.close()
    return queue_item


def run_next_refiner_job(root: Path) -> RefinerQueueItem | None:
    store = Store.for_project(root)
    try:
        payload = store.get_next_refiner_queue_item()
        if payload is None:
            return None
        item = RefinerQueueItem.from_dict(payload)
        running = replace(
            item,
            status="running",
            started_at=_now(),
            attempt_count=item.attempt_count + 1,
        )
        store.upsert_refiner_queue_item(running.to_dict())
        finished = replace(
            running,
            status="succeeded",
            finished_at=_now(),
            metadata={
                **running.metadata,
                "result": "queued refinement trigger recorded; full async worker can attach drafts",
            },
        )
        store.upsert_refiner_queue_item(finished.to_dict())
        return finished
    except Exception as exc:
        if "running" not in locals():
            raise
        failed = replace(
            running,
            status="dead_lettered" if running.attempt_count >= 3 else "failed",
            finished_at=_now(),
            last_error=str(exc),
        )
        store.upsert_refiner_queue_item(failed.to_dict())
        return failed
    finally:
        store.close()


def cancel_refiner_job(root: Path, queue_item_id: str) -> RefinerQueueItem | None:
    store = Store.for_project(root)
    try:
        payload = store.get_refiner_queue_item(queue_item_id)
        if payload is None:
            return None
        item = RefinerQueueItem.from_dict(payload)
        canceled = replace(item, status="canceled", finished_at=_now())
        store.upsert_refiner_queue_item(canceled.to_dict())
        return canceled
    finally:
        store.close()


def _now() -> str:
    return datetime.now(UTC).isoformat()
