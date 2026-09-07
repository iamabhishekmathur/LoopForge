"""Markdown reports for local issue review."""

from __future__ import annotations

from pathlib import Path

from loopforge.models.issue import Issue
from loopforge.paths import LOCAL_DIR


def issue_report_markdown(issue: Issue) -> str:
    tools = issue.metadata.get("implicated_tools", [])
    artifacts = issue.metadata.get("implicated_artifacts", [])
    return f"""# {issue.issue_id}: {issue.title}

Status: {issue.status}
Severity: {issue.severity}
Confidence: {issue.confidence:.2f}

## Ontology

- Primary: `{issue.primary_ontology_id}`
- Secondary: {", ".join(f"`{item}`" for item in issue.secondary_ontology_ids) or "None"}
- Version: `{issue.ontology_version}`

## Evidence

- Evidence traces: {", ".join(f"`{trace_id}`" for trace_id in issue.evidence_trace_ids)}
- Implicated tools: {", ".join(f"`{tool}`" for tool in tools) or "Unknown"}
- Trace observability: `{issue.trace_observability}`

## Codebase Grounding

{_artifact_lines(artifacts)}

## Root-Cause Hypotheses

{_hypothesis_lines(issue)}

## Recommended Patch Layers

{_bullet_lines(issue.recommended_patch_layers)}

## Next Action

Draft an eval that forbids the implicated side-effecting tool call before an
approval or confirmation span, then validate that evaluator before it can become
a blocking gate.
"""


def write_issue_report(root: Path, issue: Issue) -> Path:
    report_dir = root / LOCAL_DIR / "issues"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"{issue.issue_id}.md"
    path.write_text(issue_report_markdown(issue), encoding="utf-8")
    return path


def _hypothesis_lines(issue: Issue) -> str:
    if not issue.root_cause_hypotheses:
        return "- None"
    lines = []
    for hypothesis in issue.root_cause_hypotheses:
        lines.append(
            f"- `{hypothesis['label']}` ({hypothesis['confidence']:.2f}): "
            f"{hypothesis['explanation']}"
        )
    return "\n".join(lines)


def _bullet_lines(items: list[str]) -> str:
    return "\n".join(f"- `{item}`" for item in items) if items else "- None"


def _artifact_lines(artifacts: object) -> str:
    if not isinstance(artifacts, list) or not artifacts:
        return "- No implicated artifacts found in the current harness index."
    lines = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        path = artifact.get("path", "unknown")
        artifact_type = artifact.get("artifact_type", "unknown")
        confidence = float(artifact.get("confidence", 0))
        reason = artifact.get("reason", "linked by issue evidence")
        lines.append(f"- `{path}` ({artifact_type}, {confidence:.2f}): {reason}")
    return "\n".join(lines) if lines else "- No implicated artifacts found in the current harness index."
