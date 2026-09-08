"""Human-readable summaries of what LoopForge learned."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from loopforge.paths import LOCAL_DIR


def learned_report_markdown(
    *,
    issues: list[dict[str, Any]],
    operations: list[dict[str, Any]],
    confirmations: list[dict[str, Any]],
    queue_items: list[dict[str, Any]],
    issue_events: list[dict[str, Any]],
) -> str:
    ontology_counts = Counter(str(issue.get("primary_ontology_id")) for issue in issues)
    operation_status_counts = Counter(str(operation.get("status")) for operation in operations)
    scope_counts = Counter(str(operation.get("scope") or "workflow") for operation in operations)
    confirmation_counts = Counter(str(report.get("outcome")) for report in confirmations)
    queue_counts = Counter(str(item.get("status")) for item in queue_items)
    reviewer_counts = Counter(
        str(operation.get("metadata", {}).get("latest_reviewer_outcome"))
        for operation in operations
        if isinstance(operation.get("metadata"), dict)
        and operation.get("metadata", {}).get("latest_reviewer_outcome")
    )

    lines = [
        "# What LoopForge Learned",
        "",
        "## Current Pattern",
        "",
        _counter_lines(ontology_counts, "No recurring issue patterns recorded."),
        "",
        "## Refinement Health",
        "",
        _counter_lines(operation_status_counts, "No refinement operations recorded."),
        "",
        "## Refinement Scope",
        "",
        _counter_lines(scope_counts, "No scoped refinement operations recorded."),
        "",
        "## Reviewer Outcomes",
        "",
        _counter_lines(reviewer_counts, "No reviewer outcomes recorded."),
        "",
        "## Post-Merge Confirmation",
        "",
        _counter_lines(confirmation_counts, "No confirmation reports recorded."),
        "",
        "## Async Queue",
        "",
        _counter_lines(queue_counts, "No queued refinement work recorded."),
        "",
        "## Hotspots",
        "",
        _hotspot_lines(operations),
        "",
        "## Recent Reviewer Events",
        "",
        _reviewer_event_lines(issue_events),
    ]
    return "\n".join(lines)


def write_learned_report(root: Path, markdown: str) -> Path:
    report_dir = root / LOCAL_DIR / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / "LEARNED.md"
    path.write_text(markdown, encoding="utf-8")
    return path


def _counter_lines(counter: Counter[str], empty: str) -> str:
    if not counter:
        return f"- {empty}"
    return "\n".join(f"- `{name}`: {count}" for name, count in sorted(counter.items()))


def _hotspot_lines(operations: list[dict[str, Any]]) -> str:
    counts = Counter(str(operation.get("artifact_path") or "unknown") for operation in operations)
    hotspots = [(path, count) for path, count in counts.most_common() if count >= 2]
    if not hotspots:
        return "- No repeated artifact hotspots recorded."
    return "\n".join(f"- `{path}`: {count} operations" for path, count in hotspots)


def _reviewer_event_lines(events: list[dict[str, Any]]) -> str:
    reviewer_events = [
        event for event in events if event.get("event_type") == "reviewer_outcome"
    ][:5]
    if not reviewer_events:
        return "- No recent reviewer events recorded."
    lines = []
    for event in reviewer_events:
        metadata = event.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        lines.append(
            f"- `{event.get('created_at')}` `{metadata.get('outcome')}` "
            f"operation=`{metadata.get('operation_id')}` patch=`{metadata.get('patch_id')}`"
        )
    return "\n".join(lines)
