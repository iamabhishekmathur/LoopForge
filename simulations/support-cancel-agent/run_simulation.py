"""Run LoopForge against the support cancellation simulation."""

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
    ("Eval detail", ["evals", "show", "EVAL-0001"]),
    ("Refinement preview", ["refinements", "preview", "REFINE-0001-0001"]),
    ("Gate report", ["gate", "PATCH-0001"]),
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
        "# LoopForge Simulation Output",
        "",
        f"Simulation root: `{SIM_ROOT}`",
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
        sections.extend(
            [
                f"## {title}",
                "",
                "```bash",
                " ".join(["python", "-m", "loopforge", *args]),
                "```",
                "",
                f"Exit code: `{result.returncode}`",
                "",
                "```text",
                result.stdout.strip() or result.stderr.strip() or "(no output)",
                "```",
                "",
            ]
        )
        if result.returncode != 0:
            OUTPUT_PATH.write_text("\n".join(sections), encoding="utf-8")
            print(f"Simulation failed during: {title}", file=sys.stderr)
            print(result.stderr or result.stdout, file=sys.stderr)
            print(f"Wrote partial output to {OUTPUT_PATH}")
            return result.returncode

    OUTPUT_PATH.write_text("\n".join(sections), encoding="utf-8")
    print(f"Wrote simulation output to {OUTPUT_PATH}")
    print("")
    print("Key artifacts:")
    print("  .loopforge/issues/ISSUE-0001.md")
    print("  .loopforge/evals/EVAL-0001.json")
    print("  .loopforge/patches/PATCH-0001.json")
    print("  .loopforge/reports/GATE-PATCH-0001.json")
    print("  .loopforge/prs/PR-PATCH-0001.md")
    print("  .loopforge/dashboard.html")
    return 0


def reset_generated_outputs() -> None:
    local_root = SIM_ROOT / ".loopforge"
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
        "# Agent Profile: support-cancel-agent-simulation\n\n"
        "This simulation models a subscription support agent with a destructive "
        "cancellation tool and a deliberately underspecified confirmation boundary.\n\n"
        "Initial status: fixture-backed simulation.\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
