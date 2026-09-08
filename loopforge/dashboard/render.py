"""Render a static LoopForge dashboard."""

from __future__ import annotations

from html import escape
import json
from pathlib import Path
from typing import Any

from loopforge.adapters.registry import connector_statuses
from loopforge.db import Store
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
        return {
            "project_root": str(root),
            "connectors": [status.to_dict() for status in connector_statuses(root)],
            "monitor_runs": store.list_monitor_runs(),
            "issues": store.list_issues(),
            "evals": store.list_eval_examples(),
            "patches": store.list_patch_bundles(),
            "gates": store.list_gate_reports(),
            "prs": store.list_pr_artifacts(),
            "manifests": store.list_runtime_manifests(),
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
  </style>
</head>
<body>
  <header>
    <h1>LoopForge Dashboard</h1>
    <div class="muted">{escape(str(data.get("project_root", "")))}</div>
  </header>
  <main>
    {_overview(data)}
    {_table("Connectors", data.get("connectors", []), ["source_id", "source_type", "status", "message"])}
    {_table("Monitor Runs", data.get("monitor_runs", []), ["run_id", "status", "window", "counts"])}
    {_table("Issues", data.get("issues", []), ["issue_id", "severity", "confidence", "primary_ontology_id", "title"])}
    {_table("Evals", data.get("evals", []), ["eval_id", "status", "issue_id", "primary_ontology_id"])}
    {_table("Patches", data.get("patches", []), ["patch_id", "status", "issue_id", "new_eval_ids"])}
    {_table("Gates", data.get("gates", []), ["gate_report_id", "status", "recommendation", "patch_id"])}
    {_table("PR Artifacts", data.get("prs", []), ["pr_id", "status", "patch_id", "branch_name"])}
    {_table("Runtime Manifests", data.get("manifests", []), ["manifest_id", "agent_id", "agent_version", "model_name"])}
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
        ("Gates", len(data.get("gates", []))),
        ("PRs", len(data.get("prs", []))),
    ]
    cards = "\n".join(
        f'<div class="metric"><span class="muted">{escape(label)}</span><strong>{value}</strong></div>'
        for label, value in items
    )
    return f"<section><h2>Overview</h2><div class=\"grid\">{cards}</div></section>"


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
