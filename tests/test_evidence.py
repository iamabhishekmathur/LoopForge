from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


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


def write_trace(project: Path) -> None:
    (project / "traces").mkdir()
    long_answer = (
        "The user asked whether downgrade options are available. "
        "The agent correctly called the plan lookup tool, found Basic and Pro options, "
        "and explained that Basic is the least expensive downgrade path. "
    ) * 30
    trace = {
        "schema_version": "1",
        "trace_id": "tr_evidence_001",
        "started_at": "2026-09-23T00:00:00Z",
        "inputs": {"user_message": "What plans can I downgrade to?"},
        "outputs": {"assistant_message": long_answer},
        "spans": [
            {
                "span_id": "sp_1",
                "type": "tool_call",
                "name": "get_plan_options",
                "started_at": "2026-09-23T00:00:01Z",
                "input": {"customer_id": "cust_123"},
                "output": {"plans": ["Basic", "Pro"], "answer": long_answer},
                "side_effect_class": "read",
            }
        ],
    }
    (project / "traces" / "sample.jsonl").write_text(json.dumps(trace) + "\n", encoding="utf-8")


def test_evidence_archive_reduce_and_efficiency_report(tmp_path: Path) -> None:
    write_trace(tmp_path)

    init = run_loopforge(["init", "--trace-path", "traces/*.jsonl"], tmp_path)
    shadow = run_loopforge(["shadow"], tmp_path)
    archive = run_loopforge(["evidence", "archive"], tmp_path)
    evidence_list = run_loopforge(["evidence", "list"], tmp_path)
    reduce = run_loopforge(["evidence", "reduce"], tmp_path)
    receipts = run_loopforge(["evidence", "receipts"], tmp_path)
    payload = run_loopforge(["judge", "explain-payload", "tr_evidence_001"], tmp_path)
    efficiency = run_loopforge(["efficiency", "report"], tmp_path)

    assert init.returncode == 0, init.stderr
    assert shadow.returncode == 0, shadow.stderr
    assert archive.returncode == 0, archive.stderr
    assert "records: 2" in archive.stdout
    assert evidence_list.returncode == 0, evidence_list.stderr
    assert "EV-" in evidence_list.stdout
    assert reduce.returncode == 0, reduce.stderr
    assert "verified: 2" in reduce.stdout
    assert receipts.returncode == 0, receipts.stderr
    assert "verified" in receipts.stdout
    assert payload.returncode == 0, payload.stderr
    payload_json = json.loads(payload.stdout)
    assert payload_json["verified_evidence_receipts"]
    assert payload_json["evidence_policy"]["raw_evidence_is_authoritative"] is True
    assert efficiency.returncode == 0, efficiency.stderr
    assert "receipt_verification" in efficiency.stdout
    assert "cost_reduction" in efficiency.stdout


def test_evidence_show_and_receipt_show_are_addressable(tmp_path: Path) -> None:
    write_trace(tmp_path)

    assert run_loopforge(["init", "--trace-path", "traces/*.jsonl"], tmp_path).returncode == 0
    assert run_loopforge(["shadow"], tmp_path).returncode == 0
    assert run_loopforge(["evidence", "archive"], tmp_path).returncode == 0
    assert run_loopforge(["evidence", "reduce"], tmp_path).returncode == 0

    evidence_id = next(
        line.split()[0]
        for line in run_loopforge(["evidence", "list"], tmp_path).stdout.splitlines()
        if line.startswith("EV-")
    )
    receipt_id = next(
        line.split()[0]
        for line in run_loopforge(["evidence", "receipts"], tmp_path).stdout.splitlines()
        if line.startswith("ER-")
    )

    evidence = run_loopforge(["evidence", "show", evidence_id], tmp_path)
    receipt = run_loopforge(["evidence", "receipt", receipt_id], tmp_path)

    assert evidence.returncode == 0, evidence.stderr
    assert json.loads(evidence.stdout)["record"]["evidence_id"] == evidence_id
    assert receipt.returncode == 0, receipt.stderr
    assert json.loads(receipt.stdout)["receipt_id"] == receipt_id
