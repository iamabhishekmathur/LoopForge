"""Command-line interface for LoopForge."""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import sys
from pathlib import Path

from .adapters.jsonl import JsonlTraceAdapter
from . import __version__
from .config import InitOptions, configured_trace_path, initialize_project, inspect_project
from .db import Store
from .discovery.scanner import discover_harness_artifacts, write_harness_index
from .evals.artifacts import write_eval_artifacts
from .evals.generator import generate_eval_for_issue
from .evals.validator import validate_evaluator
from .issues.miner import mine_issues
from .issues.report import issue_report_markdown, write_issue_report
from .models.eval import EvalExample, EvaluatorDefinition, EvaluatorValidationRecord
from .models.issue import Issue
from .paths import PROJECT_CONFIG, find_project_root, require_project_root
from .schemas import validate_all_schemas
from .trajectories.builder import build_trajectory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="loopforge",
        description="Local-first closed-loop improvement for AI agent harnesses.",
    )
    parser.add_argument("--version", action="version", version=f"loopforge {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Initialize LoopForge in this repository.")
    init.add_argument("--project-name", default=None, help="Project name for loopforge.yaml.")
    init.add_argument(
        "--trace-path",
        default="traces/*.jsonl",
        help="Default local JSONL trace glob.",
    )
    init.add_argument("--force", action="store_true", help="Overwrite existing generated files.")

    subparsers.add_parser("doctor", help="Check local LoopForge project health.")
    subparsers.add_parser("discover", help="Discover harness artifacts in this repository.")

    shadow = subparsers.add_parser("shadow", help="Run local trace ingestion and issue mining.")
    shadow.add_argument("--last", default="24h", help="Trace window label for this run.")
    shadow.add_argument("--path", default=None, help="Override JSONL trace glob.")

    issues = subparsers.add_parser("issues", help="Inspect mined issues.")
    issue_subparsers = issues.add_subparsers(dest="issue_command", required=True)
    issue_subparsers.add_parser("list", help="List mined issues.")
    issue_show = issue_subparsers.add_parser("show", help="Show one mined issue.")
    issue_show.add_argument("issue_id")

    evals = subparsers.add_parser("evals", help="Inspect drafted evals and validators.")
    eval_subparsers = evals.add_subparsers(dest="eval_command", required=True)
    eval_subparsers.add_parser("list", help="List drafted eval examples.")
    eval_show = eval_subparsers.add_parser("show", help="Show one drafted eval example.")
    eval_show.add_argument("eval_id")

    schemas = subparsers.add_parser("schemas", help="Schema utilities.")
    schema_subparsers = schemas.add_subparsers(dest="schema_command", required=True)
    schema_subparsers.add_parser("validate", help="Parse and inspect bundled JSON schemas.")

    return parser


def command_init(args: argparse.Namespace) -> int:
    root = Path.cwd()
    project_name = args.project_name or root.name
    options = InitOptions(
        project_name=project_name,
        trace_path=args.trace_path,
        force=args.force,
    )
    try:
        created = initialize_project(root, options)
    except FileExistsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"Initialized LoopForge project in {root}")
    for path in created:
        print(f"  created {path.relative_to(root)}")
    return 0


def command_doctor(_: argparse.Namespace) -> int:
    root = find_project_root()
    if root is None:
        print(f"error: no {PROJECT_CONFIG} found", file=sys.stderr)
        return 2

    status = inspect_project(root)
    failed = [name for name, ok in status.items() if not ok]
    print(f"LoopForge project: {root}")
    for name, ok in status.items():
        marker = "ok" if ok else "missing"
        print(f"  {marker:7} {name}")

    if failed:
        print("Project health: needs attention")
        return 1
    print("Project health: ok")
    return 0


def command_schemas_validate(_: argparse.Namespace) -> int:
    require_project_root(Path.cwd()) if find_project_root() else None
    statuses = validate_all_schemas()
    if not statuses:
        print("error: no schemas found", file=sys.stderr)
        return 1

    failed = [status for status in statuses if not status.valid]
    for status in statuses:
        if status.valid:
            print(f"ok      {status.path.name}")
        else:
            print(f"error   {status.path.name}: {status.error}", file=sys.stderr)

    return 1 if failed else 0


def command_discover(_: argparse.Namespace) -> int:
    root = require_project_root(Path.cwd())
    artifacts = discover_harness_artifacts(root)
    index_path = write_harness_index(root, artifacts)
    store = Store.for_project(root)
    try:
        for artifact in artifacts:
            store.upsert_harness_artifact(artifact.to_dict())
    finally:
        store.close()

    print(f"Discovered {len(artifacts)} harness artifacts")
    print(f"  index: {index_path.relative_to(root)}")
    for artifact in artifacts:
        print(f"  {artifact.artifact_type:18} {artifact.confidence:.2f} {artifact.path}")
    return 0


def command_shadow(args: argparse.Namespace) -> int:
    root = require_project_root(Path.cwd())
    trace_path = args.path or configured_trace_path(root)
    adapter = JsonlTraceAdapter(trace_path)
    try:
        traces = adapter.read(root)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    store = Store.for_project(root)
    try:
        artifacts = discover_harness_artifacts(root)
        write_harness_index(root, artifacts)
        for artifact in artifacts:
            store.upsert_harness_artifact(artifact.to_dict())

        trajectories = []
        for trace in traces:
            trace_dict = trace.to_dict()
            trajectory = build_trajectory(trace)
            trajectories.append(trajectory)
            store.upsert_trace(trace_dict)
            store.upsert_trajectory(trajectory.to_dict())

        issues = mine_issues(traces, trajectories, artifacts)
        reports = []
        eval_count = 0
        validation_count = 0
        for issue in issues:
            generated = generate_eval_for_issue(issue, traces)
            if generated is not None:
                eval_example, evaluator = generated
                validation = validate_evaluator(issue, evaluator, traces)
                eval_paths = write_eval_artifacts(root, eval_example, evaluator, validation)
                store.upsert_eval_example(eval_example.to_dict())
                store.upsert_evaluator_definition(evaluator.to_dict())
                store.upsert_evaluator_validation_record(validation.to_dict())
                eval_count += 1
                validation_count += 1
                issue = replace(
                    issue,
                    metadata={
                        **issue.metadata,
                        "eval_artifacts": [
                            {
                                "kind": "eval",
                                "path": eval_paths["eval"].relative_to(root).as_posix(),
                                "status": eval_example.status,
                            },
                            {
                                "kind": "evaluator",
                                "path": eval_paths["evaluator"].relative_to(root).as_posix(),
                                "status": evaluator.status,
                            },
                            {
                                "kind": "validation",
                                "path": eval_paths["validation"].relative_to(root).as_posix(),
                                "status": validation.validation_status,
                            },
                        ],
                    },
                )
            issue_dict = issue.to_dict()
            store.upsert_issue(issue_dict)
            store.add_issue_event(
                {
                    "schema_version": "1",
                    "event_id": f"{issue.issue_id}-opened",
                    "issue_id": issue.issue_id,
                    "event_type": "opened",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "metadata": {"source": "shadow", "window": args.last},
                }
            )
            reports.append(write_issue_report(root, issue))
    finally:
        store.close()

    print(f"Shadow run complete for window {args.last}")
    print(f"  traces: {len(traces)}")
    print(f"  trajectories: {len(trajectories)}")
    print(f"  artifacts: {len(artifacts)}")
    print(f"  issues: {len(issues)}")
    print(f"  evals: {eval_count}")
    print(f"  validations: {validation_count}")
    for report in reports:
        print(f"  report: {report.relative_to(root)}")
    return 0


def command_issues_list(_: argparse.Namespace) -> int:
    root = require_project_root(Path.cwd())
    store = Store.for_project(root)
    try:
        issues = store.list_issues()
    finally:
        store.close()

    if not issues:
        print("No issues found.")
        return 0

    for issue in issues:
        print(
            f"{issue['issue_id']}  {issue['severity']:8}  "
            f"{issue['confidence']:.2f}  {issue['primary_ontology_id']}  {issue['title']}"
        )
    return 0


def command_issues_show(args: argparse.Namespace) -> int:
    root = require_project_root(Path.cwd())
    store = Store.for_project(root)
    try:
        issue = store.get_issue(args.issue_id)
    finally:
        store.close()

    if issue is None:
        print(f"error: issue not found: {args.issue_id}", file=sys.stderr)
        return 1

    report_path = root / ".loopforge" / "issues" / f"{args.issue_id}.md"
    if report_path.exists():
        print(report_path.read_text(encoding="utf-8"))
        return 0

    print(issue_report_markdown(Issue.from_dict(issue)))
    return 0


def command_evals_list(_: argparse.Namespace) -> int:
    root = require_project_root(Path.cwd())
    store = Store.for_project(root)
    try:
        evals = store.list_eval_examples()
    finally:
        store.close()

    if not evals:
        print("No evals found.")
        return 0

    for eval_example in evals:
        print(
            f"{eval_example['eval_id']}  {eval_example['status']:9}  "
            f"{eval_example['primary_ontology_id']}  issue={eval_example['issue_id']}"
        )
    return 0


def command_evals_show(args: argparse.Namespace) -> int:
    root = require_project_root(Path.cwd())
    store = Store.for_project(root)
    try:
        eval_example = store.get_eval_example(args.eval_id)
        evaluator = store.get_evaluator_for_eval(args.eval_id) if eval_example else None
        validation = (
            store.get_validation_for_evaluator(evaluator["evaluator_id"])
            if evaluator
            else None
        )
    finally:
        store.close()

    if eval_example is None:
        print(f"error: eval not found: {args.eval_id}", file=sys.stderr)
        return 1

    print(_eval_detail(EvalExample.from_dict(eval_example), evaluator, validation))
    return 0


def _eval_detail(
    eval_example: EvalExample,
    evaluator_payload: dict[str, object] | None,
    validation_payload: dict[str, object] | None,
) -> str:
    evaluator = (
        EvaluatorDefinition.from_dict(evaluator_payload)
        if evaluator_payload is not None
        else None
    )
    validation = (
        EvaluatorValidationRecord.from_dict(validation_payload)
        if validation_payload is not None
        else None
    )
    assertion_lines = "\n".join(
        f"- `{assertion.get('type')}`"
        + (f" tool=`{assertion.get('tool')}`" if assertion.get("tool") else "")
        for assertion in eval_example.assertions
    )
    lines = [
        f"# {eval_example.eval_id}",
        "",
        f"Status: {eval_example.status}",
        f"Issue: {eval_example.issue_id}",
        f"Ontology: `{eval_example.primary_ontology_id}` v{eval_example.ontology_version}",
        f"Source traces: {', '.join(f'`{trace_id}`' for trace_id in eval_example.source_trace_ids)}",
        "",
        "## Assertions",
        "",
        assertion_lines,
    ]
    if evaluator is not None:
        lines.extend(
            [
                "",
                "## Evaluator",
                "",
                f"- ID: `{evaluator.evaluator_id}`",
                f"- Type: `{evaluator.evaluator_type}`",
                f"- Output: `{evaluator.output_type}`",
                f"- Status: `{evaluator.status}`",
            ]
        )
    if validation is not None:
        lines.extend(
            [
                "",
                "## Validation",
                "",
                f"- Status: `{validation.validation_status}`",
                f"- Blocking eligible: `{validation.blocking_gate_eligible}`",
                f"- TPR: `{validation.true_positive_rate}`",
                f"- TNR: `{validation.true_negative_rate}`",
                f"- Precision: `{validation.precision}`",
                f"- Recall: `{validation.recall}`",
            ]
        )
    return "\n".join(lines)


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        return command_init(args)
    if args.command == "doctor":
        return command_doctor(args)
    if args.command == "discover":
        return command_discover(args)
    if args.command == "shadow":
        return command_shadow(args)
    if args.command == "issues" and args.issue_command == "list":
        return command_issues_list(args)
    if args.command == "issues" and args.issue_command == "show":
        return command_issues_show(args)
    if args.command == "evals" and args.eval_command == "list":
        return command_evals_list(args)
    if args.command == "evals" and args.eval_command == "show":
        return command_evals_show(args)
    if args.command == "schemas" and args.schema_command == "validate":
        return command_schemas_validate(args)

    parser.error("unknown command")
    return 2


def main(argv: list[str] | None = None) -> None:
    raise SystemExit(run(argv))
