"""Command-line interface for LoopForge."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import InitOptions, initialize_project, inspect_project
from .paths import PROJECT_CONFIG, find_project_root, require_project_root
from .schemas import validate_all_schemas


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


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        return command_init(args)
    if args.command == "doctor":
        return command_doctor(args)
    if args.command == "schemas" and args.schema_command == "validate":
        return command_schemas_validate(args)

    parser.error("unknown command")
    return 2


def main(argv: list[str] | None = None) -> None:
    raise SystemExit(run(argv))
