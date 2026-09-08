from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from loopforge.privacy.redaction import preview_redaction


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_loopforge(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "loopforge", *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_redaction_preview_flags_sensitive_values(tmp_path: Path) -> None:
    (tmp_path / "loopforge.yaml").write_text(
        "traces:\n  sources:\n    - id: local\n      type: jsonl\n      path: traces/*.jsonl\n",
        encoding="utf-8",
    )
    (tmp_path / "traces").mkdir()
    (tmp_path / "traces" / "trace.jsonl").write_text(
        '{"email":"person@example.com","token":"Bearer abcdefghijklmnop"}\n',
        encoding="utf-8",
    )

    preview = preview_redaction(tmp_path, path_glob="traces/*.jsonl")

    assert preview.status == "needs_review"
    assert preview.finding_count == 2
    assert {finding.kind for finding in preview.findings} == {"email", "bearer_token"}
    assert all("***" in finding.masked for finding in preview.findings)


def test_redact_preview_command_writes_report(tmp_path: Path) -> None:
    (tmp_path / "loopforge.yaml").write_text(
        "traces:\n  sources:\n    - id: local\n      type: jsonl\n      path: traces/*.jsonl\n",
        encoding="utf-8",
    )
    (tmp_path / "traces").mkdir()
    (tmp_path / "traces" / "trace.jsonl").write_text(
        '{"message":"hello"}\n',
        encoding="utf-8",
    )

    result = run_loopforge(["redact", "preview", "--path", "traces/*.jsonl"], tmp_path)

    assert result.returncode == 0, result.stderr
    assert "Status: `pass`" in result.stdout
    assert (tmp_path / ".loopforge" / "reports" / "REDACTION-PREVIEW.json").is_file()


def test_readiness_passes_for_initialized_project(tmp_path: Path) -> None:
    init = run_loopforge(["init", "--project-name", "support-agent"], tmp_path)
    readiness = run_loopforge(["readiness"], tmp_path)

    assert init.returncode == 0, init.stderr
    assert readiness.returncode == 0, readiness.stderr
    assert "Customer Test Gate" in readiness.stdout
    assert "Pass: ready for a local internal-user test" in readiness.stdout


def test_readiness_fails_when_redaction_finds_sensitive_values(tmp_path: Path) -> None:
    init = run_loopforge(["init", "--project-name", "support-agent"], tmp_path)
    (tmp_path / "traces").mkdir()
    (tmp_path / "traces" / "trace.jsonl").write_text(
        '{"message":"send receipt to person@example.com"}\n',
        encoding="utf-8",
    )

    readiness = run_loopforge(["readiness"], tmp_path)

    assert init.returncode == 0, init.stderr
    assert readiness.returncode == 1
    assert "Redaction: `needs_review`" in readiness.stdout
    assert "Fail: redaction preview found sensitive-looking values" in readiness.stdout
