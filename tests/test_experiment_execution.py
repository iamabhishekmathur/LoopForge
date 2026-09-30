from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

from loopforge.experiments.execution import CommandExecutionAdapter, validate_file_updates
from loopforge.experiments.models import (
    CandidateHypothesis,
    ExperimentCandidate,
    ExperimentCase,
)


def candidate(root: Path, content: str) -> ExperimentCandidate:
    path = root / "agent.py"
    return ExperimentCandidate(
        candidate_id="CANDIDATE-1",
        session_id="SEARCH-1",
        round_number=1,
        parent_candidate_ids=["BASELINE-1"],
        hypothesis=CandidateHypothesis("fix", "better", ["failure"], ["control"], [], "no improvement"),
        file_updates=[
            {
                "path": "agent.py",
                "expected_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "content": content,
            }
        ],
        patch_bundle={},
        status="validated",
        created_at="2026-01-01T00:00:00Z",
        proposer_id="test",
    )


def test_command_adapter_executes_updated_code_in_copy_only(tmp_path: Path) -> None:
    (tmp_path / "agent.py").write_text('ANSWER = "before"\n', encoding="utf-8")
    (tmp_path / "replay.py").write_text(
        "import json\nfrom agent import ANSWER\njson.load(__import__('sys').stdin)\n"
        "print(json.dumps({'output': {'answer': ANSWER}, 'trace': {'events': []}, "
        "'metrics': {'tool_calls': 0}, 'sandbox': {'side_effects_virtualized': True}}))\n",
        encoding="utf-8",
    )
    case = ExperimentCase(
        "CASE-1", "SEARCH-1", "TRACE-1", "search", "2026-01-01T00:00:00Z", {"query": "x"}
    )
    result = CommandExecutionAdapter(f"{sys.executable} replay.py").execute(
        tmp_path,
        candidate(tmp_path, 'ANSWER = "after"\n'),
        case,
    )

    assert result.status == "completed"
    assert result.output["answer"] == "after"
    assert (tmp_path / "agent.py").read_text(encoding="utf-8") == 'ANSWER = "before"\n'


def test_file_update_rejects_fingerprint_drift_and_protected_paths(tmp_path: Path) -> None:
    (tmp_path / "agent.py").write_text("old\n", encoding="utf-8")
    errors = validate_file_updates(
        tmp_path,
        [
            {"path": "agent.py", "expected_sha256": "wrong", "content": "new\n"},
            {"path": ".loopforge/secret", "content": "bad"},
        ],
    )
    assert any("fingerprint" in error for error in errors)
    assert any("protected" in error for error in errors)
