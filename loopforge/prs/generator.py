"""Generate local PR artifacts from gated patch bundles."""

from __future__ import annotations

import json
from pathlib import Path

from loopforge.models.issue import Issue
from loopforge.models.patch import GateReport, PatchBundle
from loopforge.models.pr import PullRequestArtifact
from loopforge.paths import LOCAL_DIR


def generate_pr_artifact(
    issue: Issue,
    patch: PatchBundle,
    gate: GateReport,
    evals: list[dict[str, object]],
    validations: list[dict[str, object]],
) -> PullRequestArtifact:
    tool = _first_tool(issue)
    title = f"Fix {issue.primary_ontology_id} for {tool or issue.issue_id}"
    branch_name = f"loopforge/{issue.issue_id.lower()}/{_slug(tool or issue.primary_ontology_id)}"
    body = _body(issue, patch, gate, evals, validations)
    return PullRequestArtifact(
        pr_id=f"PR-{patch.patch_id}",
        patch_id=patch.patch_id,
        issue_id=issue.issue_id,
        title=title,
        body=body,
        branch_name=branch_name,
        metadata={
            "dry_run": True,
            "ai_drafted": True,
            "requires_human_approval": True,
        },
    )


def write_pr_artifact(root: Path, pr: PullRequestArtifact) -> dict[str, Path]:
    pr_dir = root / LOCAL_DIR / "prs"
    pr_dir.mkdir(parents=True, exist_ok=True)
    json_path = pr_dir / f"{pr.pr_id}.json"
    md_path = pr_dir / f"{pr.pr_id}.md"
    json_path.write_text(json.dumps(pr.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(pr_markdown(pr), encoding="utf-8")
    return {"json": json_path, "markdown": md_path}


def pr_markdown(pr: PullRequestArtifact) -> str:
    return f"""# {pr.title}

Branch: `{pr.branch_name}`
Status: `{pr.status}`
Patch: `{pr.patch_id}`
Issue: `{pr.issue_id}`

{pr.body}
"""


def _body(
    issue: Issue,
    patch: PatchBundle,
    gate: GateReport,
    evals: list[dict[str, object]],
    validations: list[dict[str, object]],
) -> str:
    evidence = "\n".join(f"- `{trace_id}`" for trace_id in issue.evidence_trace_ids)
    targets = "\n".join(
        f"- `{artifact.get('path')}` ({artifact.get('artifact_type')})"
        for artifact in patch.target_artifacts
    )
    eval_lines = "\n".join(
        f"- `{item.get('eval_id')}`: {item.get('primary_ontology_id')}"
        for item in evals
    ) or "- None"
    validation_lines = "\n".join(
        f"- `{item.get('evaluator_id')}`: {item.get('validation_status')}, "
        f"blocking={item.get('blocking_gate_eligible')}"
        for item in validations
    ) or "- None"
    suites = "\n".join(f"- {suite['status']}: `{suite['name']}`" for suite in gate.suites)
    return f"""## Summary

Drafts a focused harness patch for `{issue.primary_ontology_id}`.

## Evidence

{evidence}

## Codebase Grounding

{targets}

## Changes

{patch.risk_assessment}

## Eval Coverage

{eval_lines}

## Evaluator Validation

{validation_lines}

## Gate Results

- Report: `{gate.gate_report_id}`
- Status: `{gate.status}`
- Recommendation: `{gate.recommendation}`

{suites}

## Rollback

{patch.rollback_plan}

## Residual Risk

This is a generated dry-run PR artifact. A human reviewer must inspect the diff,
eval coverage, validation record, and gate report before opening or merging a
real pull request.

## Diff

```diff
{patch.diff.rstrip()}
```
"""


def _first_tool(issue: Issue) -> str | None:
    tools = issue.metadata.get("implicated_tools", [])
    if isinstance(tools, list) and tools:
        return str(tools[0])
    return None


def _slug(value: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "patch"
