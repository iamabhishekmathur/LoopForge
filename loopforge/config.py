"""Project configuration generation and lightweight inspection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .paths import LOCAL_DIR, PROJECT_CONFIG


DEFAULT_LOCAL_DIRS = [
    "analysis",
    "cache",
    "connectors",
    "evals",
    "index",
    "issues",
    "manifests",
    "patches",
    "prs",
    "reports",
    "rollbacks",
    "setup",
    "traces",
]

SUPPORTED_FRAMEWORKS = {
    "generic",
    "langgraph",
    "openai-agents",
    "vercel-ai",
    "llamaindex",
    "crewai",
    "autogen",
    "mastra",
    "pydantic-ai",
}


@dataclass(frozen=True)
class InitOptions:
    project_name: str
    trace_path: str = "traces/*.jsonl"
    framework: str = "generic"
    force: bool = False


def default_config_text(options: InitOptions) -> str:
    return f"""version: 1
project:
  name: {options.project_name}
  framework: {options.framework}

monitor:
  enabled: true
  schedule: "every 6 hours"
  trace_window: "24 hours"
  min_issue_confidence: 0.78
  min_patch_confidence: 0.82
  ai_draft_all_artifacts: true
  open_prs: false
  max_prs_per_day: 3
  autonomy_level: 1

refinement:
  enabled: true
  cadence: "after_monitor_run"
  default_scope: workflow
  max_candidate_operations: 5

analysis:
  max_traces_per_scan: 1000
  max_full_traces_per_scan: 75
  max_model_calls_per_scan: 250
  max_estimated_cost_usd_per_scan: 10
  analysis_level: standard

connect:
  auto_detect_trace_source: true
  auto_generate_setup_prs: true

discovery:
  enabled: true
  refresh_on_git_change: true
  min_artifact_confidence: 0.75
  include:
    - .
  exclude:
    - .git/**
    - node_modules/**
    - .venv/**
    - .loopforge/**

traces:
  sources:
    - id: local-jsonl
      type: jsonl
      path: {options.trace_path}

runtime_manifest:
  required_for_behavior_patches: true
  min_coverage_percent: 90
  prefer_manifest_over_static_index: true

redaction:
  mode: strict
  hash_stable_ids: true
  external_llm_allowed: false

gates:
  default_suite: core
  require_human_approval: true
  max_prompt_diff_lines: 80
  max_cost_regression_percent: 10

evaluator_validation:
  required_for_blocking_gates: true
  min_true_positive_rate: 0.90
  min_true_negative_rate: 0.90
  freeze_judge_prompts: true
  require_train_dev_test_split: true
"""


def framework_recipe_text(framework: str) -> str:
    recipes = {
        "langgraph": (
            "Capture graph node names, tool calls, state transitions, and checkpointer IDs. "
            "Emit a runtime manifest when the graph is compiled or deployed."
        ),
        "openai-agents": (
            "Capture agent name, model settings, instructions hash, tool schemas, handoffs, "
            "guardrails, and run/item spans."
        ),
        "vercel-ai": (
            "Capture model settings, system prompt hash, tool definitions, stream events, "
            "and server action side-effect boundaries."
        ),
        "llamaindex": (
            "Capture query engine, retriever, tool specs, index version, source nodes, and "
            "response synthesizer spans."
        ),
        "crewai": (
            "Capture crew, agent role, task, tool calls, delegation events, and process mode."
        ),
        "autogen": (
            "Capture group chat turns, speaker selection, tool/function calls, handoff state, "
            "and termination conditions."
        ),
        "mastra": (
            "Capture workflow runs, agent instructions, tool definitions, memory/retrieval "
            "configuration, and step transitions."
        ),
        "pydantic-ai": (
            "Capture agent system prompt, dependency context, tool schemas, structured output "
            "validators, and result validation spans."
        ),
        "generic": (
            "Capture system/developer prompts, tool schemas, routing decisions, permissions, "
            "retrieval/context inputs, tool calls, outputs, feedback, and runtime manifest IDs."
        ),
    }
    guidance = recipes.get(framework, recipes["generic"])
    return f"""# LoopForge Framework Recipe

Framework: {framework}

## Trace Instrumentation

{guidance}

## Runtime Manifest

Emit stable hashes or source references for prompts, tools, policies, context builders,
retrievers, memory interfaces, eval suites, and agent graph definitions.

## First Closed Loop

1. Run `loopforge discover`.
2. Run `loopforge monitor --once`.
3. Run `loopforge queue run-next`.
4. Review `loopforge refinements preview OPERATION_ID`.
5. Run `loopforge gate PATCH_ID`.
"""


def default_agent_profile_text(project_name: str) -> str:
    return f"""# Agent Profile

Project: {project_name}

This file is generated project context for LoopForge. It is not the source of
truth for agent behavior; code, harness artifacts, runtime manifests, traces,
and evals remain authoritative.

## Agent Purpose

Unknown.

## User Workflows

Unknown.

## Runtime Architecture

Unknown.

## Harness Summary

Unknown.

## Trace Shape Guide

Unknown.

## Ontology Priorities

Unknown.

## Known Failure Patterns

Unknown.

## Reviewer Preferences

Unknown.

## Trust Qualification

Initial status: unqualified.

## Observability Gaps

Unknown.
"""


def initialize_project(root: Path, options: InitOptions) -> list[Path]:
    created: list[Path] = []
    config_path = root / PROJECT_CONFIG
    local_dir = root / LOCAL_DIR
    profile_path = local_dir / "agent-profile.md"
    framework_path = local_dir / "setup" / f"{options.framework}-recipe.md"

    if config_path.exists() and not options.force:
        raise FileExistsError(f"{config_path} already exists. Use --force to overwrite.")

    local_dir.mkdir(exist_ok=True)
    created.append(local_dir)

    for name in DEFAULT_LOCAL_DIRS:
        path = local_dir / name
        path.mkdir(exist_ok=True)
        created.append(path)

    config_path.write_text(default_config_text(options), encoding="utf-8")
    created.append(config_path)

    if not profile_path.exists() or options.force:
        profile_path.write_text(
            default_agent_profile_text(options.project_name),
            encoding="utf-8",
        )
        created.append(profile_path)

    if not framework_path.exists() or options.force:
        framework_path.parent.mkdir(exist_ok=True)
        framework_path.write_text(framework_recipe_text(options.framework), encoding="utf-8")
        created.append(framework_path)

    return created


def inspect_project(root: Path) -> dict[str, bool]:
    local_dir = root / LOCAL_DIR
    return {
        "config": (root / PROJECT_CONFIG).is_file(),
        "local_dir": local_dir.is_dir(),
        "agent_profile": (local_dir / "agent-profile.md").is_file(),
        **{f"dir_{name}": (local_dir / name).is_dir() for name in DEFAULT_LOCAL_DIRS},
    }


def configured_trace_path(root: Path) -> str | None:
    """Read the first configured JSONL trace path from loopforge.yaml.

    The MVP avoids a YAML dependency, so this intentionally reads only the
    simple `path:` shape generated by `loopforge init`.
    """
    config_path = root / PROJECT_CONFIG
    if not config_path.exists():
        return "traces/*.jsonl"

    in_traces = False
    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if stripped == "traces:":
            in_traces = True
            continue
        if in_traces and raw_line and not raw_line.startswith(" "):
            in_traces = False
        if in_traces and stripped.startswith("path:"):
            value = stripped.split(":", 1)[1].strip()
            return value.strip("\"'")
    return None


def configured_open_prs(root: Path) -> bool:
    value = _first_scalar_config_value(root, "open_prs")
    return str(value).lower() == "true"


def configured_max_prs_per_day(root: Path) -> int:
    value = _first_scalar_config_value(root, "max_prs_per_day")
    if value is None:
        return 3
    try:
        return int(value)
    except ValueError:
        return 0


def configured_monitor_schedule(root: Path) -> str:
    return _first_scalar_config_value(root, "schedule") or "every 6 hours"


def configured_monitor_trace_window(root: Path) -> str:
    return _first_scalar_config_value(root, "trace_window") or "24 hours"


def configured_refiner_target_scope(root: Path) -> str:
    value = _first_scalar_config_value(root, "default_scope") or "workflow"
    return value if value in {"shadow", "workflow", "project", "org"} else "workflow"


def _first_scalar_config_value(root: Path, key: str) -> str | None:
    config_path = root / PROJECT_CONFIG
    if not config_path.exists():
        return None

    prefix = f"{key}:"
    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if stripped.startswith(prefix):
            value = stripped.split(":", 1)[1].strip()
            return value.strip("\"'")
    return None
