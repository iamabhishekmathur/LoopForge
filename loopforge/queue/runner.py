"""Repository-local async refiner queue helpers."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from loopforge.db import Store
from loopforge.models.issue import Issue
from loopforge.models.queue import RefinerQueueItem
from loopforge.patching.generator import write_patch_bundle
from loopforge.refinements.ledger import write_refinement_operations
from loopforge.refinements.refiner import refine_issue


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
        result = _draft_refinements_for_queue_item(root, store, running)
        finished = replace(
            running,
            status="succeeded",
            finished_at=_now(),
            metadata={
                **running.metadata,
                "result": "drafted refinement work from queued monitor trigger",
                **result,
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


def _draft_refinements_for_queue_item(
    root: Path,
    store: Store,
    item: RefinerQueueItem,
) -> dict[str, object]:
    max_operations = item.budget.get("max_candidate_operations", 5)
    drafted_patches = 0
    drafted_operations = 0
    skipped_issues = 0
    processed_issue_ids: list[str] = []
    abstentions: list[dict[str, object]] = []

    for issue_payload in store.list_issues():
        if drafted_operations >= max_operations:
            break
        issue = Issue.from_dict(issue_payload)
        if issue.status not in {"open", "proposed"}:
            skipped_issues += 1
            continue
        eval_ids = [
            str(eval_payload["eval_id"])
            for eval_payload in store.list_evals_for_issue(issue.issue_id)
        ]
        draft = refine_issue(root, issue, eval_ids)
        if draft.patch is None:
            abstentions.append(
                {
                    "issue_id": issue.issue_id,
                    "reason": draft.reason,
                    "abstentions": draft.abstentions,
                }
            )
            continue
        write_patch_bundle(root, draft.patch)
        store.upsert_patch_bundle(draft.patch.to_dict())
        write_refinement_operations(root, draft.operations)
        for operation in draft.operations:
            store.upsert_refinement_operation(operation.to_dict())
        proposed_issue = replace(issue, status="proposed")
        store.upsert_issue(proposed_issue.to_dict())
        drafted_patches += 1
        drafted_operations += len(draft.operations)
        processed_issue_ids.append(issue.issue_id)

    return {
        "drafted_patches": drafted_patches,
        "drafted_operations": drafted_operations,
        "processed_issue_ids": processed_issue_ids,
        "skipped_issues": skipped_issues,
        "abstentions": abstentions[:5],
    }
