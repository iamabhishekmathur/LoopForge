"""Run LoopForge against the Acme multi-agent platform simulation."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


SIM_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SIM_ROOT.parents[1]
OUTPUT_PATH = SIM_ROOT / "simulation-output.md"
LOCAL_DIRS = [
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
    "resolutions",
    "rollbacks",
    "setup",
    "traces",
]


COMMANDS = [
    ("Connector list", ["connectors", "list"]),
    ("Connector doctor", ["connectors", "doctor"]),
    ("Readiness gate", ["readiness"]),
    ("Harness discovery", ["discover"]),
    ("Monitor once", ["monitor", "--once", "--last", "24h"]),
    ("Run async refiner", ["queue", "run-next"]),
    ("Issue detail", ["issues", "show", "ISSUE-0001"]),
    ("Resolution plan", ["issues", "resolution-plan", "ISSUE-0001"]),
    ("Eval detail", ["evals", "show", "EVAL-0001"]),
    ("Refinement preview", ["refinements", "preview", "REFINE-0001-0001"]),
    ("Gate report", ["gate", "PATCH-0001"]),
    ("Resolution plan after gate", ["issues", "resolution-plan", "ISSUE-0001"]),
    ("Dry-run PR artifact", ["pr", "--dry-run", "PATCH-0001"]),
    ("Learned report", ["learned"]),
    ("Dashboard build", ["dashboard", "build"]),
]


def main() -> int:
    reset_generated_outputs()
    ensure_loopforge_skeleton()
    env = os.environ.copy()
    pythonpath = str(REPO_ROOT)
    if env.get("PYTHONPATH"):
        pythonpath = pythonpath + os.pathsep + env["PYTHONPATH"]
    env["PYTHONPATH"] = pythonpath

    sections = [
        "# Acme Agent Platform Simulation Output",
        "",
        f"Simulation root: `{SIM_ROOT}`",
        "",
        "This run uses a fixture-backed LangSmith source with 12 traces across support, billing, and escalation agents.",
        "",
    ]
    for title, args in COMMANDS:
        command = [sys.executable, "-m", "loopforge", *args]
        result = subprocess.run(
            command,
            cwd=SIM_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        sections.extend(command_section(title, args, result))
        if result.returncode != 0:
            OUTPUT_PATH.write_text("\n".join(sections), encoding="utf-8")
            print(f"Simulation failed during: {title}", file=sys.stderr)
            print(result.stderr or result.stdout, file=sys.stderr)
            print(f"Wrote partial output to {OUTPUT_PATH}")
            return result.returncode

    sections.extend(
        [
            "## Interpretation",
            "",
            "- LoopForge should catch the recurring unsafe cancellation pattern.",
            "- Retrieval misses and escalation noise are intentionally present but are not yet mined as first-class issue families.",
            "- The resolution plan should keep the reviewer focused on runtime enforcement and trace instrumentation because the policy already says confirmation is required.",
            "",
        ]
    )
    OUTPUT_PATH.write_text("\n".join(sections), encoding="utf-8")
    print(f"Wrote simulation output to {OUTPUT_PATH}")
    print("")
    print("Key artifacts:")
    print("  .loopforge/issues/ISSUE-0001.md")
    print("  .loopforge/resolutions/RESOLVE-0001.md")
    print("  .loopforge/evals/EVAL-0001.json")
    print("  .loopforge/patches/PATCH-0001.json")
    print("  .loopforge/reports/GATE-PATCH-0001.json")
    print("  .loopforge/prs/PR-PATCH-0001.md")
    print("  .loopforge/dashboard.html")
    return 0


def command_section(
    title: str,
    args: list[str],
    result: subprocess.CompletedProcess[str],
) -> list[str]:
    output = result.stdout.strip()
    if result.stderr.strip():
        output = (output + "\n" + result.stderr.strip()).strip()
    return [
        f"## {title}",
        "",
        "```bash",
        " ".join(["python", "-m", "loopforge", *args]),
        "```",
        "",
        f"Exit code: `{result.returncode}`",
        "",
        "```text",
        output or "(no output)",
        "```",
        "",
    ]


def reset_generated_outputs() -> None:
    local_root = SIM_ROOT / ".loopforge"
    if local_root.exists():
        for path in local_root.rglob("*"):
            if path.is_file():
                path.unlink()
        for path in sorted(local_root.rglob("*"), reverse=True):
            if path.is_dir() and not any(path.iterdir()):
                path.rmdir()
    if OUTPUT_PATH.exists():
        OUTPUT_PATH.unlink()


def ensure_loopforge_skeleton() -> None:
    local_root = SIM_ROOT / ".loopforge"
    local_root.mkdir(exist_ok=True)
    for name in LOCAL_DIRS:
        (local_root / name).mkdir(exist_ok=True)
    (local_root / "agent-profile.md").write_text(
        "# Agent Profile: acme-agent-platform-simulation\n\n"
        "This simulation models a multi-agent customer support platform with "
        "support, billing, and escalation agents. The runtime has an intentional "
        "authorization enforcement flaw so LoopForge can test grounded resolution "
        "planning against a realistic harness.\n\n"
        "Initial status: fixture-backed simulation.\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
