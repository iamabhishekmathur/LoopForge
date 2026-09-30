"""Render a static LoopForge dashboard."""

from __future__ import annotations

from html import escape
import json
from pathlib import Path
from typing import Any

from loopforge.adapters.registry import connector_statuses
from loopforge.db import Store
from loopforge.evidence.archive import list_evidence
from loopforge.evidence.reducer import list_receipts
from loopforge.paths import LOCAL_DIR


def build_dashboard(root: Path) -> Path:
    payload = collect_dashboard_data(root)
    path = root / LOCAL_DIR / "dashboard.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_dashboard(payload), encoding="utf-8")
    return path


def collect_dashboard_data(root: Path) -> dict[str, Any]:
    store = Store.for_project(root)
    try:
        search_sessions = store.list_search_sessions()
        return {
            "project_root": str(root),
            "connectors": [status.to_dict() for status in connector_statuses(root)],
            "monitor_runs": store.list_monitor_runs(),
            "issues": store.list_issues(),
            "evals": store.list_eval_examples(),
            "patches": store.list_patch_bundles(),
            "refinements": store.list_refinement_operations(),
            "gates": store.list_gate_reports(),
            "replays": store.list_replay_reports(),
            "confirmations": store.list_confirmation_reports(),
            "queue_items": store.list_refiner_queue_items(),
            "prs": store.list_pr_artifacts(),
            "manifests": store.list_runtime_manifests(),
            "states": store.list_harness_states(),
            "evidence": [record.to_dict() for record in list_evidence(root)],
            "receipts": [receipt.to_dict() for receipt in list_receipts(root)],
            "search_sessions": search_sessions,
            "experiment_candidates": [
                candidate
                for session in search_sessions
                for candidate in store.list_experiment_candidates(session["session_id"])
            ],
            "candidate_evaluations": [
                evaluation
                for session in search_sessions
                for evaluation in store.list_candidate_evaluations(session["session_id"])
            ],
            "pareto_snapshots": [
                snapshot
                for session in search_sessions
                for snapshot in store.list_pareto_snapshots(session["session_id"])
            ],
            "search_events": [
                event
                for session in search_sessions
                for event in store.list_search_events(session["session_id"])
            ],
        }
    finally:
        store.close()


def render_dashboard(data: dict[str, Any]) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LoopForge Dashboard</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8fa;
      --panel: #ffffff;
      --text: #17191c;
      --muted: #5e6673;
      --line: #d8dde6;
      --good: #0f7b4f;
      --warn: #9a5b00;
      --bad: #b42318;
      --accent: #155eef;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    header {{
      padding: 24px 32px 16px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }}
    h1 {{ margin: 0 0 4px; font-size: 24px; }}
    h2 {{ margin: 0 0 12px; font-size: 16px; }}
    main {{ padding: 24px 32px 40px; display: grid; gap: 20px; }}
    section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }}
    .metric {{ border: 1px solid var(--line); border-radius: 6px; padding: 12px; }}
    .metric strong {{ display: block; font-size: 24px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; padding: 8px 6px; border-top: 1px solid var(--line); vertical-align: top; }}
    th {{ color: var(--muted); font-weight: 600; }}
    code {{ background: #eef1f6; padding: 1px 4px; border-radius: 4px; }}
    .status-succeeded, .status-pass, .status-ready, .status-opened {{ color: var(--good); font-weight: 600; }}
    .status-warn, .status-drafted, .status-setup_only {{ color: var(--warn); font-weight: 600; }}
    .status-failed, .status-reject, .status-needs_credentials, .status-invalid {{ color: var(--bad); font-weight: 600; }}
    .muted {{ color: var(--muted); }}
    .timeline {{ position: relative; margin: 8px 0 0 8px; padding-left: 24px; }}
    .timeline::before {{ content: ""; position: absolute; left: 6px; top: 5px; bottom: 5px; width: 2px; background: var(--line); }}
    .event {{ position: relative; padding: 0 0 14px 0; }}
    .event::before {{ content: ""; position: absolute; left: -22px; top: 5px; width: 10px; height: 10px; border-radius: 50%; background: var(--panel); border: 2px solid var(--accent); }}
    .event strong {{ display: inline-block; margin-right: 8px; }}
    .lineage {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0; }}
    .candidate {{ border: 1px solid var(--line); border-radius: 6px; padding: 8px 10px; min-width: 180px; }}
    details summary {{ cursor: pointer; font-weight: 600; }}
  </style>
</head>
<body>
  <header>
    <h1>LoopForge Dashboard</h1>
    <div class="muted">{escape(str(data.get("project_root", "")))}</div>
  </header>
  <main>
    {_overview(data)}
    {_search_experiments(data)}
    {_table("Connectors", data.get("connectors", []), ["source_id", "source_type", "status", "message"])}
    {_table("Monitor Runs", data.get("monitor_runs", []), ["run_id", "status", "window", "counts"])}
    {_table("Issues", data.get("issues", []), ["issue_id", "severity", "confidence", "primary_ontology_id", "title"])}
    {_table("Evals", data.get("evals", []), ["eval_id", "status", "issue_id", "primary_ontology_id"])}
    {_table("Patches", data.get("patches", []), ["patch_id", "status", "issue_id", "new_eval_ids"])}
    {_table("Refinement Operations", data.get("refinements", []), ["operation_id", "status", "scope", "operation_type", "component_type", "patch_id"])}
    {_table("Gates", data.get("gates", []), ["gate_report_id", "status", "recommendation", "patch_id"])}
    {_table("Replay Reports", data.get("replays", []), ["replay_id", "status", "patch_id", "passed_cases", "failed_cases"])}
    {_table("Confirmation Reports", data.get("confirmations", []), ["confirmation_id", "outcome", "patch_id", "recommendation"])}
    {_table("Refiner Queue", data.get("queue_items", []), ["queue_item_id", "status", "trigger", "target_scope", "trace_window"])}
    {_table("PR Artifacts", data.get("prs", []), ["pr_id", "status", "patch_id", "branch_name"])}
    {_table("Runtime Manifests", data.get("manifests", []), ["manifest_id", "agent_id", "agent_version", "model_name"])}
    {_table("Harness States", data.get("states", []), ["state_id", "source", "confidence", "operation_ids"])}
    {_table("Evidence Archive", data.get("evidence", []), ["evidence_id", "source_type", "source_id", "byte_count"])}
    {_table("Evidence Receipts", data.get("receipts", []), ["receipt_id", "verification_status", "compression_ratio", "evidence_id"])}
  </main>
</body>
</html>
"""


def _overview(data: dict[str, Any]) -> str:
    items = [
        ("Connectors", len(data.get("connectors", []))),
        ("Runs", len(data.get("monitor_runs", []))),
        ("Issues", len(data.get("issues", []))),
        ("Patches", len(data.get("patches", []))),
        ("Refinements", len(data.get("refinements", []))),
        ("Gates", len(data.get("gates", []))),
        ("Confirmations", len(data.get("confirmations", []))),
        ("Queue", len(data.get("queue_items", []))),
        ("PRs", len(data.get("prs", []))),
        ("States", len(data.get("states", []))),
        ("Evidence", len(data.get("evidence", []))),
        ("Receipts", len(data.get("receipts", []))),
        ("Search Sessions", len(data.get("search_sessions", []))),
        ("Candidates", len(data.get("experiment_candidates", []))),
    ]
    cards = "\n".join(
        f'<div class="metric"><span class="muted">{escape(label)}</span><strong>{value}</strong></div>'
        for label, value in items
    )
    return f"<section><h2>Overview</h2><div class=\"grid\">{cards}</div></section>"


def _search_experiments(data: dict[str, Any]) -> str:
    sessions = data.get("search_sessions", [])
    if not sessions:
        return '<section><h2>Harness Experiments</h2><p class="muted">No search sessions.</p></section>'
    candidates = data.get("experiment_candidates", [])
    evaluations = data.get("candidate_evaluations", [])
    snapshots = data.get("pareto_snapshots", [])
    events = data.get("search_events", [])
    blocks = []
    for session in sessions:
        session_id = session.get("session_id")
        session_candidates = [item for item in candidates if item.get("session_id") == session_id]
        latest_frontier = [item for item in snapshots if item.get("session_id") == session_id]
        frontier_ids = set((latest_frontier[-1] if latest_frontier else {}).get("candidate_ids") or [])
        lineage = "".join(
            _candidate_card(candidate, evaluations, frontier_ids)
            for candidate in session_candidates
        )
        timeline = "".join(
            _event_item(event)
            for event in events
            if event.get("session_id") == session_id
        )
        blocks.append(
            f'<details open><summary>{escape(str(session_id))} · '
            f'{escape(str(session.get("status")))}</summary>'
            f'<div class="lineage">{lineage}</div>'
            f'<div class="timeline">{timeline}</div></details>'
        )
    return f'<section><h2>Harness Experiments</h2>{"".join(blocks)}</section>'


def _candidate_card(
    candidate: dict[str, Any],
    evaluations: list[dict[str, Any]],
    frontier_ids: set[str],
) -> str:
    candidate_id = str(candidate.get("candidate_id"))
    combined = next(
        (
            item
            for item in reversed(evaluations)
            if item.get("candidate_id") == candidate_id
            and (item.get("metadata") or {}).get("staged_holdout") is True
        ),
        {},
    )
    objectives = combined.get("objectives") or {}
    marker = " · frontier" if candidate_id in frontier_ids else ""
    return (
        '<div class="candidate">'
        f'<strong>{escape(candidate_id)}</strong><br>'
        f'<span class="status-{escape(str(candidate.get("status")))}">'
        f'{escape(str(candidate.get("status")))}{marker}</span><br>'
        f'<span class="muted">quality {escape(str(objectives.get("quality", "-")))} · '
        f'resolution {escape(str(objectives.get("issue_resolution", "-")))}</span>'
        '</div>'
    )


def _event_item(event: dict[str, Any]) -> str:
    return (
        '<div class="event">'
        f'<strong>{escape(str(event.get("event_type")))}</strong>'
        f'<span class="muted">{escape(str(event.get("created_at", "")))}</span><br>'
        f'<span>{escape(str(event.get("candidate_id") or "session"))}</span>'
        '</div>'
    )


def _table(title: str, rows: list[Any], columns: list[str]) -> str:
    if not rows:
        return f"<section><h2>{escape(title)}</h2><p class=\"muted\">No records.</p></section>"
    headers = "".join(f"<th>{escape(column)}</th>" for column in columns)
    body = "\n".join(_row(row, columns) for row in rows if isinstance(row, dict))
    return f"<section><h2>{escape(title)}</h2><table><thead><tr>{headers}</tr></thead><tbody>{body}</tbody></table></section>"


def _row(row: dict[str, Any], columns: list[str]) -> str:
    cells = "".join(f"<td>{_cell(column, row.get(column))}</td>" for column in columns)
    return f"<tr>{cells}</tr>"


def _cell(column: str, value: Any) -> str:
    if value is None:
        return '<span class="muted">None</span>'
    if column == "status":
        status = str(value)
        return f'<span class="status-{escape(status)}">{escape(status)}</span>'
    if isinstance(value, (dict, list)):
        return f"<code>{escape(json.dumps(value, sort_keys=True))}</code>"
    return escape(str(value))
