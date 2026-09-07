from __future__ import annotations

from pathlib import Path

import pytest

from loopforge.adapters.jsonl import JsonlTraceAdapter


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "support-agent"


def test_jsonl_adapter_reads_fixture_traces() -> None:
    traces = JsonlTraceAdapter("../traces/support-agent-cancellation.jsonl").read(FIXTURE_ROOT)

    assert len(traces) == 10
    assert traces[0].trace_id == "tr_fail_001"
    assert traces[0].spans[1].name == "cancel_subscription"


def test_jsonl_adapter_reports_line_numbers(tmp_path: Path) -> None:
    trace_path = tmp_path / "bad.jsonl"
    trace_path.write_text("{bad json}\n", encoding="utf-8")

    with pytest.raises(ValueError) as exc:
        JsonlTraceAdapter("bad.jsonl").read(tmp_path)

    assert "bad.jsonl:1" in str(exc.value)
