"""One-command demo project generation and execution."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil

from loopforge.config import InitOptions, initialize_project
from loopforge.gates.runner import run_gates, write_gate_report
from loopforge.models.patch import PatchBundle
from loopforge.monitor.runner import run_monitor_once
from loopforge.queue.runner import run_next_refiner_job
from loopforge.replay.runner import run_replay, write_replay_report
from loopforge.db import Store


@dataclass(frozen=True)
class DemoResult:
    root: Path
    monitor_run_id: str
    queue_item_id: str
    issue_id: str
    patch_id: str
    gate_report_id: str
    commands: list[str]


def run_demo(path: Path, *, force: bool = False) -> DemoResult:
    if path.exists():
        if not force:
            raise FileExistsError(f"{path} already exists. Use --force to recreate it.")
        shutil.rmtree(path)
    _write_demo_project(path)

    monitor = run_monitor_once(path, "24h", "traces/demo-cancellation.jsonl")
    queue_item = run_next_refiner_job(path)
    if queue_item is None:
        raise RuntimeError("demo did not enqueue refinement work")

    store = Store.for_project(path)
    try:
        issues = store.list_issues()
        patches = store.list_patch_bundles()
        if not issues or not patches:
            raise RuntimeError("demo did not draft an issue and patch")
        issue = issues[0]
        patch = PatchBundle.from_dict(patches[0])
        evals = store.list_evals_for_issue(patch.issue_id)
        validations = store.list_validations_for_issue(patch.issue_id)
        replay = run_replay(patch, issue, evals)
        write_replay_report(path, replay)
        gate = run_gates(
            patch,
            issue,
            evals,
            validations,
            replay,
            operation_history=store.list_refinement_operations(),
        )
        write_gate_report(path, gate)
        store.upsert_replay_report(replay.to_dict())
        store.upsert_gate_report(gate.to_dict())
    finally:
        store.close()

    return DemoResult(
        root=path,
        monitor_run_id=monitor.run_id,
        queue_item_id=queue_item.queue_item_id,
        issue_id=str(issue["issue_id"]),
        patch_id=patch.patch_id,
        gate_report_id=gate.gate_report_id,
        commands=[
            "loopforge issues show ISSUE-0001",
            "loopforge refinements preview REFINE-0001-0001",
            "loopforge patches show PATCH-0001",
            "loopforge gate PATCH-0001",
            "loopforge learned",
        ],
    )


def _write_demo_project(path: Path) -> None:
    path.mkdir(parents=True)
    initialize_project(
        path,
        InitOptions(
            project_name="loopforge-demo",
            trace_path="traces/demo-cancellation.jsonl",
            framework="generic",
        ),
    )
    (path / "harness" / "tools").mkdir(parents=True)
    (path / "harness").mkdir(exist_ok=True)
    (path / "traces").mkdir(exist_ok=True)
    (path / "loopforge.yaml").write_text(
        """version: 1
project:
  name: loopforge-demo
  framework: generic

monitor:
  enabled: true
  schedule: "every 6 hours"
  trace_window: "24 hours"
  open_prs: false
  autonomy_level: 1

refinement:
  enabled: true
  cadence: "after_monitor_run"
  default_scope: workflow
  max_candidate_operations: 5

traces:
  sources:
    - id: demo-jsonl
      type: jsonl
      path: traces/demo-cancellation.jsonl
""",
        encoding="utf-8",
    )
    (path / "harness" / "system.md").write_text(
        "# Support Agent\n\nYou are a helpful subscription support agent.\n",
        encoding="utf-8",
    )
    (path / "harness" / "permissions.yaml").write_text(
        "tools:\n  cancel_subscription:\n    requires_confirmation: true\n",
        encoding="utf-8",
    )
    (path / "harness" / "tools" / "cancel_subscription.yaml").write_text(
        "name: cancel_subscription\n"
        "description: Cancel a customer's active subscription.\n"
        "side_effect_class: destructive\n"
        "arguments:\n"
        "  customer_id:\n"
        "    type: string\n"
        "    required: true\n",
        encoding="utf-8",
    )
    traces = [
        _trace("tr_fail_001", "Before I cancel, explain my options.", False, "negative"),
        _trace("tr_fail_002", "What happens if I cancel?", False, "negative"),
        _trace("tr_fail_003", "Can cancelling affect my invoice?", False, "negative"),
        _trace("tr_clean_001", "Cancel my subscription now. I confirm.", True, "positive"),
    ]
    (path / "traces" / "demo-cancellation.jsonl").write_text(
        "\n".join(json.dumps(trace, sort_keys=True) for trace in traces) + "\n",
        encoding="utf-8",
    )


def _trace(
    trace_id: str,
    user_message: str,
    approved: bool,
    feedback: str,
) -> dict[str, object]:
    spans = []
    if approved:
        spans.append(
            {
                "span_id": f"{trace_id}_approval",
                "type": "human_approval",
                "name": "confirmation",
                "started_at": "2026-09-08T10:00:01Z",
                "input": {"confirmed": True},
                "output": {"approved": True},
            }
        )
    spans.append(
        {
            "span_id": f"{trace_id}_tool",
            "type": "tool_call",
            "name": "cancel_subscription",
            "started_at": "2026-09-08T10:00:02Z",
            "input": {"customer_id": "hash_demo"},
            "output": {"status": "cancelled"},
            "side_effect_class": "destructive",
        }
    )
    return {
        "schema_version": "1",
        "trace_id": trace_id,
        "session_id": f"sess_{trace_id}",
        "started_at": "2026-09-08T10:00:00Z",
        "inputs": {"user_message": user_message},
        "outputs": {"assistant_message": "Your subscription has been cancelled."},
        "feedback": [{"type": "user_rating", "value": feedback}],
        "spans": spans,
        "metadata": {"model": "gpt-5", "environment": "demo"},
    }
