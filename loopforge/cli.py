"""Command-line interface for LoopForge."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
import sys
from pathlib import Path

from . import __version__
from .adapters.registry import connector_statuses
from .config import InitOptions, initialize_project, inspect_project
from .dashboard.render import build_dashboard
from .db import Store
from .discovery.manifest import build_runtime_manifest, write_runtime_manifest
from .discovery.scanner import discover_harness_artifacts, write_harness_index
from .issues.report import issue_report_markdown, write_issue_report
from .models.eval import EvalExample, EvaluatorDefinition, EvaluatorValidationRecord
from .models.harness import HarnessArtifact
from .models.issue import Issue
from .models.monitor import MonitorRun
from .models.patch import PatchBundle, GateReport
from .models.pr import PullRequestArtifact
from .models.refinement import RefinementOperation
from .models.runtime import RuntimeHarnessManifest
from .models.state import HarnessStateSnapshot
from .paths import PROJECT_CONFIG, find_project_root, require_project_root
from .patching.generator import write_patch_bundle
from .prs.generator import generate_pr_artifact, pr_markdown, write_pr_artifact
from .prs.opener import PrOpenError, open_pull_request
from .refinements.ledger import write_refinement_operations
from .refinements.refiner import refine_issue
from .gates.runner import run_gates, write_gate_report
from .replay.runner import run_replay, write_replay_report
from .schemas import validate_all_schemas
from .monitor.runner import iter_monitor_runs, parse_schedule_seconds
from .shadow.runner import run_shadow_pipeline
from .state.graph import build_harness_state_snapshot, write_harness_state_snapshot


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

    onboard = subparsers.add_parser("onboard", help="Run the fast LoopForge adoption path.")
    onboard.add_argument("--project-name", default=None, help="Project name for new config.")
    onboard.add_argument("--trace-path", default=None, help="JSONL trace glob for new config or first run.")
    onboard.add_argument("--last", default=None, help="Trace window for the first monitor run.")
    onboard.add_argument("--skip-monitor", action="store_true", help="Stop after discovery and manifest.")

    subparsers.add_parser("doctor", help="Check local LoopForge project health.")
    subparsers.add_parser("discover", help="Discover harness artifacts in this repository.")

    dashboard = subparsers.add_parser("dashboard", help="Build a local read-only dashboard.")
    dashboard_subparsers = dashboard.add_subparsers(dest="dashboard_command", required=True)
    dashboard_subparsers.add_parser("build", help="Write .loopforge/dashboard.html.")

    manifest = subparsers.add_parser("manifest", help="Inspect runtime harness manifests.")
    manifest_subparsers = manifest.add_subparsers(dest="manifest_command", required=True)
    manifest_subparsers.add_parser("write", help="Write a runtime manifest from discovery.")
    manifest_subparsers.add_parser("list", help="List runtime manifests.")
    manifest_show = manifest_subparsers.add_parser("show", help="Show one runtime manifest.")
    manifest_show.add_argument("manifest_id", nargs="?")

    states = subparsers.add_parser("states", help="Inspect harness state snapshots.")
    state_subparsers = states.add_subparsers(dest="state_command", required=True)
    state_subparsers.add_parser("list", help="List harness state snapshots.")
    state_show = state_subparsers.add_parser("show", help="Show one harness state snapshot.")
    state_show.add_argument("state_id", nargs="?")

    connectors = subparsers.add_parser("connectors", help="Inspect trace connectors.")
    connector_subparsers = connectors.add_subparsers(dest="connector_command", required=True)
    connector_subparsers.add_parser("list", help="List configured trace connectors.")
    connector_subparsers.add_parser("doctor", help="Validate trace connector readiness.")

    shadow = subparsers.add_parser("shadow", help="Run local trace ingestion and issue mining.")
    shadow.add_argument("--last", default="24h", help="Trace window label for this run.")
    shadow.add_argument("--path", default=None, help="Override JSONL trace glob.")

    monitor = subparsers.add_parser("monitor", help="Run or inspect automatic monitoring.")
    monitor.add_argument("--once", action="store_true", help="Run one monitor cycle and exit.")
    monitor.add_argument("--max-runs", type=int, default=None, help="Run N monitor cycles and exit.")
    monitor.add_argument("--interval", default=None, help="Override schedule, such as '30s' or '5m'.")
    monitor.add_argument("--last", default=None, help="Override configured trace window.")
    monitor.add_argument("--path", default=None, help="Override configured trace source path.")
    monitor.add_argument("--list-runs", action="store_true", help="List persisted monitor runs.")
    monitor.add_argument("--show-run", default=None, help="Show one persisted monitor run.")

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

    propose = subparsers.add_parser("propose", help="Draft a local patch bundle for an issue.")
    propose.add_argument("issue_id")
    propose.add_argument(
        "--layer",
        choices=[
            "tool_description",
            "permission_policy",
            "system_prompt",
            "skill",
            "routing_policy",
            "context_policy",
            "retrieval_policy",
            "evaluator",
        ],
        default=None,
        help="Preferred patch layer.",
    )

    patches = subparsers.add_parser("patches", help="Inspect drafted patch bundles.")
    patch_subparsers = patches.add_subparsers(dest="patch_command", required=True)
    patch_subparsers.add_parser("list", help="List drafted patch bundles.")
    patch_show = patch_subparsers.add_parser("show", help="Show one drafted patch bundle.")
    patch_show.add_argument("patch_id")

    refinements = subparsers.add_parser("refinements", help="Inspect refinement operations.")
    refinement_subparsers = refinements.add_subparsers(dest="refinement_command", required=True)
    refinement_subparsers.add_parser("list", help="List drafted refinement operations.")
    refinement_show = refinement_subparsers.add_parser("show", help="Show one refinement operation.")
    refinement_show.add_argument("operation_id")

    gate = subparsers.add_parser("gate", help="Run local acceptance gates for a patch bundle.")
    gate.add_argument("patch_id")

    replay = subparsers.add_parser("replay", help="Run replay simulation for a patch bundle.")
    replay.add_argument("patch_id")

    pr = subparsers.add_parser("pr", help="Draft or open pull request artifacts.")
    pr.add_argument("--dry-run", action="store_true", help="Write local PR JSON and Markdown only.")
    pr.add_argument(
        "pr_args",
        nargs="+",
        help="Use '--dry-run PATCH_ID' or 'open PR_ID'.",
    )

    prs = subparsers.add_parser("prs", help="Inspect drafted pull request artifacts.")
    pr_subparsers = prs.add_subparsers(dest="pr_command", required=True)
    pr_subparsers.add_parser("list", help="List drafted pull request artifacts.")
    pr_show = pr_subparsers.add_parser("show", help="Show one drafted pull request artifact.")
    pr_show.add_argument("pr_id")

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


def command_onboard(args: argparse.Namespace) -> int:
    root = Path.cwd()
    created = []
    if find_project_root() is None:
        created = initialize_project(
            root,
            InitOptions(
                project_name=args.project_name or root.name,
                trace_path=args.trace_path or "traces/*.jsonl",
            ),
        )
        print(f"Initialized LoopForge project in {root}")
        print(f"  created: {len(created)} paths")
    else:
        root = require_project_root(root)
        print(f"Using LoopForge project in {root}")

    statuses = connector_statuses(root)
    ready_sources = [status for status in statuses if status.status == "ready"]
    print(f"Connectors: {len(ready_sources)}/{len(statuses)} ready")
    for status in statuses:
        print(f"  {status.source_id}: {status.status} ({status.message})")

    artifacts = discover_harness_artifacts(root)
    index_path = write_harness_index(root, artifacts)
    manifest = build_runtime_manifest(root, artifacts)
    manifest_path = write_runtime_manifest(root, manifest)
    state, state_paths = _write_discovered_harness_state(root, artifacts, manifest)
    store = Store.for_project(root)
    try:
        for artifact in artifacts:
            store.upsert_harness_artifact(artifact.to_dict())
        store.upsert_runtime_manifest(manifest.to_dict())
        store.upsert_harness_state(state.to_dict())
    finally:
        store.close()
    print(f"Discovery: {len(artifacts)} artifacts")
    print(f"  index: {index_path.relative_to(root)}")
    print(f"  manifest: {manifest_path.relative_to(root)}")
    print(f"  state: {state_paths['state'].relative_to(root)}")

    if args.skip_monitor:
        print("Monitor: skipped")
        return 0

    run = next(
        iter_monitor_runs(
            root,
            window=args.last,
            trace_path=args.trace_path,
            max_runs=1,
        )
    )
    print(_monitor_run_summary(run))
    if run.status == "failed":
        return 1
    print("Onboarding complete.")
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
    manifest = build_runtime_manifest(root, artifacts)
    manifest_path = write_runtime_manifest(root, manifest)
    state, state_paths = _write_discovered_harness_state(root, artifacts, manifest)
    store = Store.for_project(root)
    try:
        for artifact in artifacts:
            store.upsert_harness_artifact(artifact.to_dict())
        store.upsert_runtime_manifest(manifest.to_dict())
        store.upsert_harness_state(state.to_dict())
    finally:
        store.close()

    print(f"Discovered {len(artifacts)} harness artifacts")
    print(f"  index: {index_path.relative_to(root)}")
    print(f"  manifest: {manifest_path.relative_to(root)}")
    print(f"  state: {state_paths['state'].relative_to(root)}")
    for artifact in artifacts:
        print(f"  {artifact.artifact_type:18} {artifact.confidence:.2f} {artifact.path}")
    return 0


def command_dashboard_build(_: argparse.Namespace) -> int:
    root = require_project_root(Path.cwd())
    path = build_dashboard(root)
    print(f"Built dashboard {path.relative_to(root)}")
    return 0


def command_manifest_write(_: argparse.Namespace) -> int:
    root = require_project_root(Path.cwd())
    artifacts = discover_harness_artifacts(root)
    manifest = build_runtime_manifest(root, artifacts)
    path = write_runtime_manifest(root, manifest)
    state, state_paths = _write_discovered_harness_state(root, artifacts, manifest)
    store = Store.for_project(root)
    try:
        store.upsert_runtime_manifest(manifest.to_dict())
        store.upsert_harness_state(state.to_dict())
    finally:
        store.close()

    print(f"Wrote runtime manifest {manifest.manifest_id}")
    print(f"  path: {path.relative_to(root)}")
    print(f"  state: {state_paths['state'].relative_to(root)}")
    print(f"  artifacts: {len(artifacts)}")
    return 0


def command_manifest_list(_: argparse.Namespace) -> int:
    root = require_project_root(Path.cwd())
    store = Store.for_project(root)
    try:
        manifests = store.list_runtime_manifests()
    finally:
        store.close()

    if not manifests:
        print("No runtime manifests found.")
        return 0

    for manifest in manifests:
        metadata = manifest.get("metadata") or {}
        print(
            f"{manifest['manifest_id']}  agent={manifest['agent_id']}  "
            f"artifacts={metadata.get('artifact_count', 0)}"
        )
    return 0


def command_manifest_show(args: argparse.Namespace) -> int:
    root = require_project_root(Path.cwd())
    manifest_id = args.manifest_id
    store = Store.for_project(root)
    try:
        if manifest_id:
            manifest = store.get_runtime_manifest(manifest_id)
        else:
            manifests = store.list_runtime_manifests()
            manifest = manifests[0] if manifests else None
    finally:
        store.close()

    if manifest is None:
        print("error: runtime manifest not found", file=sys.stderr)
        return 1

    print(json.dumps(RuntimeHarnessManifest.from_dict(manifest).to_dict(), indent=2, sort_keys=True))
    return 0


def command_states_list(_: argparse.Namespace) -> int:
    root = require_project_root(Path.cwd())
    store = Store.for_project(root)
    try:
        states = store.list_harness_states()
    finally:
        store.close()

    if not states:
        print("No harness state snapshots found.")
        return 0

    for state in states:
        print(
            f"{state['state_id']}  {state['source']:18}  "
            f"confidence={float(state['confidence']):.2f}  "
            f"artifacts={len(state.get('artifact_refs') or [])}  "
            f"operations={len(state.get('operation_ids') or [])}"
        )
    return 0


def command_states_show(args: argparse.Namespace) -> int:
    root = require_project_root(Path.cwd())
    state_id = args.state_id
    store = Store.for_project(root)
    try:
        if state_id:
            state = store.get_harness_state(state_id)
        else:
            states = store.list_harness_states()
            state = states[0] if states else None
    finally:
        store.close()

    if state is None:
        print("error: harness state not found", file=sys.stderr)
        return 1

    print(json.dumps(HarnessStateSnapshot.from_dict(state).to_dict(), indent=2, sort_keys=True))
    return 0


def command_connectors_list(_: argparse.Namespace) -> int:
    root = require_project_root(Path.cwd())
    statuses = connector_statuses(root)
    for status in statuses:
        print(
            f"{status.source_id}  {status.source_type:14}  "
            f"{status.status:17}  {status.message}"
        )
    return 0


def command_connectors_doctor(_: argparse.Namespace) -> int:
    root = require_project_root(Path.cwd())
    statuses = connector_statuses(root)
    failed = []
    for status in statuses:
        ok = status.status in {"ready", "setup_only"}
        marker = "ok" if ok else "error"
        print(
            f"{marker:5} {status.source_id}  {status.source_type:14}  "
            f"{status.status:17}  {status.message}"
        )
        if not ok:
            failed.append(status)
    return 1 if failed else 0


def command_shadow(args: argparse.Namespace) -> int:
    root = require_project_root(Path.cwd())
    try:
        result = run_shadow_pipeline(root, args.last, args.path)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Shadow run complete for window {args.last}")
    print(f"  traces: {result.trace_count}")
    print(f"  trajectories: {result.trajectory_count}")
    print(f"  artifacts: {result.artifact_count}")
    print(f"  issues: {result.issue_count}")
    print(f"  evals: {result.eval_count}")
    print(f"  validations: {result.validation_count}")
    for report in result.report_paths:
        print(f"  report: {report.relative_to(root)}")
    return 0


def command_monitor(args: argparse.Namespace) -> int:
    root = require_project_root(Path.cwd())
    if args.list_runs:
        return command_monitor_list_runs(root)
    if args.show_run:
        return command_monitor_show_run(root, args.show_run)

    max_runs = 1 if args.once else args.max_runs
    interval_seconds = parse_schedule_seconds(args.interval) if args.interval else None
    if max_runs is None:
        print("Starting LoopForge monitor. Press Ctrl-C to stop.")

    try:
        for run in iter_monitor_runs(
            root,
            window=args.last,
            trace_path=args.path,
            interval_seconds=interval_seconds,
            max_runs=max_runs,
        ):
            print(_monitor_run_summary(run))
            if run.status == "failed":
                return 1
    except KeyboardInterrupt:
        print("Monitor stopped.")
        return 130
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


def command_monitor_list_runs(root: Path) -> int:
    store = Store.for_project(root)
    try:
        runs = store.list_monitor_runs()
    finally:
        store.close()

    if not runs:
        print("No monitor runs found.")
        return 0

    for run in runs:
        counts = run.get("counts") or {}
        print(
            f"{run['run_id']}  {run['status']:9}  "
            f"traces={counts.get('traces', 0)}  issues={counts.get('issues', 0)}"
        )
    return 0


def command_monitor_show_run(root: Path, run_id: str) -> int:
    store = Store.for_project(root)
    try:
        payload = store.get_monitor_run(run_id)
    finally:
        store.close()

    if payload is None:
        print(f"error: monitor run not found: {run_id}", file=sys.stderr)
        return 1

    print(_monitor_run_detail(MonitorRun.from_dict(payload)))
    return 0


def _monitor_run_summary(run: MonitorRun) -> str:
    counts = run.counts
    summary = (
        f"Monitor run {run.run_id}: {run.status} "
        f"traces={counts.get('traces', 0)} issues={counts.get('issues', 0)} "
        f"evals={counts.get('evals', 0)} validations={counts.get('validations', 0)}"
    )
    if run.error:
        summary += f" error={run.error}"
    return summary


def _monitor_run_detail(run: MonitorRun) -> str:
    lines = [
        f"# {run.run_id}",
        "",
        f"Status: `{run.status}`",
        f"Started: `{run.started_at}`",
        f"Finished: `{run.finished_at}`",
        f"Window: `{run.window}`",
        f"Trace path: `{run.trace_path}`",
        "",
        "## Counts",
        "",
    ]
    if run.counts:
        lines.extend(f"- {key}: `{value}`" for key, value in sorted(run.counts.items()))
    else:
        lines.append("- None")
    if run.error:
        lines.extend(["", "## Error", "", run.error])
    reports = run.metadata.get("reports", [])
    if isinstance(reports, list) and reports:
        lines.extend(["", "## Reports", ""])
        lines.extend(f"- `{report}`" for report in reports)
    return "\n".join(lines)


def _write_discovered_harness_state(
    root: Path,
    artifacts: list[HarnessArtifact],
    manifest: RuntimeHarnessManifest,
) -> tuple[HarnessStateSnapshot, dict[str, Path]]:
    state = build_harness_state_snapshot(artifacts, manifest)
    paths = write_harness_state_snapshot(root, state)
    return state, paths


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


def command_propose(args: argparse.Namespace) -> int:
    root = require_project_root(Path.cwd())
    store = Store.for_project(root)
    try:
        issue_payload = store.get_issue(args.issue_id)
        if issue_payload is None:
            print(f"error: issue not found: {args.issue_id}", file=sys.stderr)
            return 1
        evals = store.list_evals_for_issue(args.issue_id)
        issue = Issue.from_dict(issue_payload)
        draft = refine_issue(
            root,
            issue,
            [str(eval_example["eval_id"]) for eval_example in evals],
            preferred_layer=args.layer,
        )
        if draft.patch is None:
            print(f"error: {draft.reason}", file=sys.stderr)
            return 1
        patch = draft.patch
        operations = draft.operations
        paths = write_patch_bundle(root, patch)
        operation_paths = write_refinement_operations(root, operations)
        store.upsert_patch_bundle(patch.to_dict())
        for operation in operations:
            store.upsert_refinement_operation(operation.to_dict())
    finally:
        store.close()

    print(f"Drafted patch {patch.patch_id}")
    print(f"  issue: {patch.issue_id}")
    print(f"  refiner: {draft.selected_pass}")
    print(f"  status: {patch.status}")
    print(f"  bundle: {paths['json'].relative_to(root)}")
    print(f"  diff: {paths['diff'].relative_to(root)}")
    print(f"  refinements: {len(operations)}")
    for path in operation_paths:
        print(f"    {path.relative_to(root)}")
    return 0


def command_patches_list(_: argparse.Namespace) -> int:
    root = require_project_root(Path.cwd())
    store = Store.for_project(root)
    try:
        patches = store.list_patch_bundles()
    finally:
        store.close()

    if not patches:
        print("No patches found.")
        return 0

    for patch in patches:
        print(
            f"{patch['patch_id']}  {patch['status']:7}  issue={patch['issue_id']}  "
            f"evals={','.join(patch.get('new_eval_ids') or [])}"
        )
    return 0


def command_patches_show(args: argparse.Namespace) -> int:
    root = require_project_root(Path.cwd())
    store = Store.for_project(root)
    try:
        patch_payload = store.get_patch_bundle(args.patch_id)
        gate_payload = store.get_gate_report_for_patch(args.patch_id)
    finally:
        store.close()

    if patch_payload is None:
        print(f"error: patch not found: {args.patch_id}", file=sys.stderr)
        return 1

    print(_patch_detail(PatchBundle.from_dict(patch_payload), gate_payload))
    return 0


def command_refinements_list(_: argparse.Namespace) -> int:
    root = require_project_root(Path.cwd())
    store = Store.for_project(root)
    try:
        operations = store.list_refinement_operations()
    finally:
        store.close()

    if not operations:
        print("No refinement operations found.")
        return 0

    for operation in operations:
        print(
            f"{operation['operation_id']}  {operation['status']:7}  "
            f"{operation['operation_type']:6}  {operation['component_type']:16}  "
            f"patch={operation['patch_id']}  issue={operation['issue_id']}"
        )
    return 0


def command_refinements_show(args: argparse.Namespace) -> int:
    root = require_project_root(Path.cwd())
    store = Store.for_project(root)
    try:
        operation_payload = store.get_refinement_operation(args.operation_id)
    finally:
        store.close()

    if operation_payload is None:
        print(f"error: refinement operation not found: {args.operation_id}", file=sys.stderr)
        return 1

    print(_refinement_detail(RefinementOperation.from_dict(operation_payload)))
    return 0


def command_gate(args: argparse.Namespace) -> int:
    root = require_project_root(Path.cwd())
    store = Store.for_project(root)
    try:
        patch_payload = store.get_patch_bundle(args.patch_id)
        if patch_payload is None:
            print(f"error: patch not found: {args.patch_id}", file=sys.stderr)
            return 1
        patch = PatchBundle.from_dict(patch_payload)
        issue = store.get_issue(patch.issue_id)
        if issue is None:
            print(f"error: issue not found for patch: {patch.issue_id}", file=sys.stderr)
            return 1
        evals = store.list_evals_for_issue(patch.issue_id)
        validations = store.list_validations_for_issue(patch.issue_id)
        replay_report = run_replay(patch, issue, evals)
        write_replay_report(root, replay_report)
        operation_history = store.list_refinement_operations()
        report = run_gates(
            patch,
            issue,
            evals,
            validations,
            replay_report,
            operation_history=operation_history,
        )
        report_path = write_gate_report(root, report)
        patch_status = "gated" if report.status in {"pass", "warn", "needs_human_review"} else "rejected"
        store.upsert_patch_bundle(replace(patch, status=patch_status).to_dict())
        operation_status = "gated" if patch_status == "gated" else "rejected"
        for operation_payload in store.list_refinement_operations_for_patch(patch.patch_id):
            operation = RefinementOperation.from_dict(operation_payload)
            updated_operation = replace(
                operation,
                status=operation_status,
                metadata={
                    **operation.metadata,
                    "latest_gate_report_id": report.gate_report_id,
                    "latest_gate_status": report.status,
                },
            )
            write_refinement_operations(root, [updated_operation])
            store.upsert_refinement_operation(updated_operation.to_dict())
        store.upsert_replay_report(replay_report.to_dict())
        store.upsert_gate_report(report.to_dict())
    finally:
        store.close()

    print(f"Gate report {report.gate_report_id}")
    print(f"  patch: {report.patch_id}")
    print(f"  status: {report.status}")
    print(f"  recommendation: {report.recommendation}")
    print(f"  report: {report_path.relative_to(root)}")
    for suite in report.suites:
        print(f"  {suite['status']:6} {suite['name']}")
    return 0 if report.status in {"pass", "warn", "needs_human_review"} else 1


def command_replay(args: argparse.Namespace) -> int:
    root = require_project_root(Path.cwd())
    store = Store.for_project(root)
    try:
        patch_payload = store.get_patch_bundle(args.patch_id)
        if patch_payload is None:
            print(f"error: patch not found: {args.patch_id}", file=sys.stderr)
            return 1
        patch = PatchBundle.from_dict(patch_payload)
        issue = store.get_issue(patch.issue_id)
        if issue is None:
            print(f"error: issue not found for patch: {patch.issue_id}", file=sys.stderr)
            return 1
        evals = store.list_evals_for_issue(patch.issue_id)
        report = run_replay(patch, issue, evals)
        path = write_replay_report(root, report)
        store.upsert_replay_report(report.to_dict())
    finally:
        store.close()

    print(f"Replay report {report.replay_id}")
    print(f"  patch: {report.patch_id}")
    print(f"  status: {report.status}")
    print(f"  passed: {report.passed_cases}")
    print(f"  failed: {report.failed_cases}")
    print(f"  report: {path.relative_to(root)}")
    return 0 if report.status == "pass" else 1


def command_pr(args: argparse.Namespace) -> int:
    if args.dry_run:
        if len(args.pr_args) != 1:
            print("error: usage is loopforge pr --dry-run PATCH_ID", file=sys.stderr)
            return 2
        return command_pr_dry_run(args.pr_args[0])

    if len(args.pr_args) == 2 and args.pr_args[0] == "open":
        return command_pr_open(args.pr_args[1])

    print("error: usage is loopforge pr --dry-run PATCH_ID or loopforge pr open PR_ID", file=sys.stderr)
    return 2


def command_pr_dry_run(patch_id: str) -> int:
    root = require_project_root(Path.cwd())
    store = Store.for_project(root)
    try:
        patch_payload = store.get_patch_bundle(patch_id)
        if patch_payload is None:
            print(f"error: patch not found: {patch_id}", file=sys.stderr)
            return 1
        patch = PatchBundle.from_dict(patch_payload)
        if patch.status != "gated":
            print(
                f"error: patch must pass gates before PR draft: {patch_id}",
                file=sys.stderr,
            )
            return 1

        issue_payload = store.get_issue(patch.issue_id)
        if issue_payload is None:
            print(f"error: issue not found for patch: {patch.issue_id}", file=sys.stderr)
            return 1

        gate_payload = store.get_gate_report_for_patch(patch.patch_id)
        if gate_payload is None:
            print(f"error: no gate report found for patch: {patch.patch_id}", file=sys.stderr)
            return 1
        gate = GateReport.from_dict(gate_payload)
        if gate.status not in {"pass", "warn", "needs_human_review"}:
            print(
                f"error: latest gate is not eligible for PR draft: {gate.status}",
                file=sys.stderr,
            )
            return 1

        evals = store.list_evals_for_issue(patch.issue_id)
        validations = store.list_validations_for_issue(patch.issue_id)
        pr = generate_pr_artifact(
            Issue.from_dict(issue_payload),
            patch,
            gate,
            evals,
            validations,
        )
        paths = write_pr_artifact(root, pr)
        store.upsert_pr_artifact(pr.to_dict())
    finally:
        store.close()

    print(f"Drafted PR artifact {pr.pr_id}")
    print(f"  patch: {pr.patch_id}")
    print(f"  branch: {pr.branch_name}")
    print(f"  markdown: {paths['markdown'].relative_to(root)}")
    print(f"  json: {paths['json'].relative_to(root)}")
    return 0


def command_pr_open(pr_id: str) -> int:
    root = require_project_root(Path.cwd())
    store = Store.for_project(root)
    try:
        pr_payload = store.get_pr_artifact(pr_id)
        if pr_payload is None:
            print(f"error: PR artifact not found: {pr_id}", file=sys.stderr)
            return 1
        pr = PullRequestArtifact.from_dict(pr_payload)

        patch_payload = store.get_patch_bundle(pr.patch_id)
        if patch_payload is None:
            print(f"error: patch not found for PR artifact: {pr.patch_id}", file=sys.stderr)
            return 1
        patch = PatchBundle.from_dict(patch_payload)

        try:
            opened = open_pull_request(root, pr, patch)
        except PrOpenError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        opened_pr = replace(
            pr,
            status="opened",
            metadata={
                **pr.metadata,
                "dry_run": False,
                "github_url": opened.url,
                "base_branch": opened.base_branch,
                "commit_sha": opened.commit_sha,
            },
        )
        paths = write_pr_artifact(root, opened_pr)
        store.upsert_pr_artifact(opened_pr.to_dict())
    finally:
        store.close()

    print(f"Opened PR artifact {opened_pr.pr_id}")
    print(f"  url: {opened.url}")
    print(f"  branch: {opened.branch_name}")
    print(f"  commit: {opened.commit_sha}")
    print(f"  markdown: {paths['markdown'].relative_to(root)}")
    print(f"  json: {paths['json'].relative_to(root)}")
    return 0


def command_prs_list(_: argparse.Namespace) -> int:
    root = require_project_root(Path.cwd())
    store = Store.for_project(root)
    try:
        prs = store.list_pr_artifacts()
    finally:
        store.close()

    if not prs:
        print("No PR artifacts found.")
        return 0

    for pr in prs:
        print(
            f"{pr['pr_id']}  {pr['status']:7}  patch={pr['patch_id']}  "
            f"branch={pr['branch_name']}"
        )
    return 0


def command_prs_show(args: argparse.Namespace) -> int:
    root = require_project_root(Path.cwd())
    store = Store.for_project(root)
    try:
        pr_payload = store.get_pr_artifact(args.pr_id)
    finally:
        store.close()

    if pr_payload is None:
        print(f"error: PR artifact not found: {args.pr_id}", file=sys.stderr)
        return 1

    pr_path = root / ".loopforge" / "prs" / f"{args.pr_id}.md"
    if pr_path.exists():
        print(pr_path.read_text(encoding="utf-8"))
        return 0

    print(pr_markdown(PullRequestArtifact.from_dict(pr_payload)))
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


def _patch_detail(patch: PatchBundle, gate_payload: dict[str, object] | None) -> str:
    target_lines = "\n".join(
        f"- `{artifact.get('path')}` ({artifact.get('artifact_type')}, "
        f"{float(artifact.get('confidence') or 0):.2f})"
        for artifact in patch.target_artifacts
    )
    lines = [
        f"# {patch.patch_id}",
        "",
        f"Status: {patch.status}",
        f"Issue: {patch.issue_id}",
        f"Eval coverage: {', '.join(f'`{eval_id}`' for eval_id in patch.new_eval_ids) or 'None'}",
        "",
        "## Target Artifacts",
        "",
        target_lines,
        "",
        "## Risk",
        "",
        patch.risk_assessment,
        "",
        "## Rollback",
        "",
        patch.rollback_plan,
        "",
        "## Diff",
        "",
        "```diff",
        patch.diff.rstrip(),
        "```",
    ]
    if gate_payload is not None:
        gate = GateReport.from_dict(gate_payload)
        lines.extend(
            [
                "",
                "## Latest Gate",
                "",
                f"- ID: `{gate.gate_report_id}`",
                f"- Status: `{gate.status}`",
                f"- Recommendation: `{gate.recommendation}`",
            ]
        )
    return "\n".join(lines)


def _refinement_detail(operation: RefinementOperation) -> str:
    lines = [
        f"# {operation.operation_id}",
        "",
        f"Status: {operation.status}",
        f"Operation: `{operation.operation_type}`",
        f"Component: `{operation.component_type}`",
        f"Artifact: `{operation.artifact_path}`",
        f"Issue: `{operation.issue_id}`",
        f"Patch: `{operation.patch_id}`",
        f"Confidence: `{operation.confidence}`",
        f"Created: `{operation.created_at}`",
        "",
        "## Rationale",
        "",
        operation.rationale,
        "",
        "## Evidence",
        "",
        f"- Traces: {', '.join(f'`{trace_id}`' for trace_id in operation.source_trace_ids) or 'None'}",
        f"- Evals: {', '.join(f'`{eval_id}`' for eval_id in operation.source_eval_ids) or 'None'}",
        "",
        "## Diff Summary",
        "",
        operation.diff_summary,
        "",
        "## Provenance",
        "",
        "```json",
        json.dumps(operation.provenance, indent=2, sort_keys=True),
        "```",
    ]
    return "\n".join(lines)


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        return command_init(args)
    if args.command == "onboard":
        return command_onboard(args)
    if args.command == "doctor":
        return command_doctor(args)
    if args.command == "discover":
        return command_discover(args)
    if args.command == "dashboard" and args.dashboard_command == "build":
        return command_dashboard_build(args)
    if args.command == "manifest" and args.manifest_command == "write":
        return command_manifest_write(args)
    if args.command == "manifest" and args.manifest_command == "list":
        return command_manifest_list(args)
    if args.command == "manifest" and args.manifest_command == "show":
        return command_manifest_show(args)
    if args.command == "states" and args.state_command == "list":
        return command_states_list(args)
    if args.command == "states" and args.state_command == "show":
        return command_states_show(args)
    if args.command == "connectors" and args.connector_command == "list":
        return command_connectors_list(args)
    if args.command == "connectors" and args.connector_command == "doctor":
        return command_connectors_doctor(args)
    if args.command == "shadow":
        return command_shadow(args)
    if args.command == "monitor":
        return command_monitor(args)
    if args.command == "issues" and args.issue_command == "list":
        return command_issues_list(args)
    if args.command == "issues" and args.issue_command == "show":
        return command_issues_show(args)
    if args.command == "evals" and args.eval_command == "list":
        return command_evals_list(args)
    if args.command == "evals" and args.eval_command == "show":
        return command_evals_show(args)
    if args.command == "propose":
        return command_propose(args)
    if args.command == "patches" and args.patch_command == "list":
        return command_patches_list(args)
    if args.command == "patches" and args.patch_command == "show":
        return command_patches_show(args)
    if args.command == "refinements" and args.refinement_command == "list":
        return command_refinements_list(args)
    if args.command == "refinements" and args.refinement_command == "show":
        return command_refinements_show(args)
    if args.command == "gate":
        return command_gate(args)
    if args.command == "replay":
        return command_replay(args)
    if args.command == "pr":
        return command_pr(args)
    if args.command == "prs" and args.pr_command == "list":
        return command_prs_list(args)
    if args.command == "prs" and args.pr_command == "show":
        return command_prs_show(args)
    if args.command == "schemas" and args.schema_command == "validate":
        return command_schemas_validate(args)

    parser.error("unknown command")
    return 2


def main(argv: list[str] | None = None) -> None:
    raise SystemExit(run(argv))
