from __future__ import annotations

from pathlib import Path

from loopforge.adapters.jsonl import JsonlTraceAdapter
from loopforge.analysis.authorization import diagnosis_from_dict
from loopforge.analysis.judge import JsonFileJudge, LocalFallbackJudge, write_diagnosis
from loopforge.discovery.scanner import discover_harness_artifacts
from loopforge.issues.miner import mine_issues
from loopforge.trajectories.builder import build_trajectory


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "fixtures" / "support-agent"


def test_json_file_judge_can_override_fallback_diagnosis() -> None:
    traces = JsonlTraceAdapter("../traces/support-agent-cancellation.jsonl").read(FIXTURE_ROOT)
    trajectories = [build_trajectory(trace) for trace in traces]
    artifacts = discover_harness_artifacts(FIXTURE_ROOT)
    judge = JsonFileJudge(REPO_ROOT / "tests" / "fixtures" / "model-diagnosis.json")

    issues = mine_issues(traces, trajectories, artifacts, judge=judge)

    assert issues[0].confidence == 0.91
    assert issues[0].root_cause_hypotheses[0]["label"] == "model_observed_missing_confirmation"
    assert issues[0].metadata["diagnosis"]["calibration"]["judge"] == "json_file"


def test_local_fallback_judge_returns_structured_diagnosis() -> None:
    traces = JsonlTraceAdapter("../traces/support-agent-cancellation.jsonl").read(FIXTURE_ROOT)
    trajectories = [build_trajectory(trace) for trace in traces]
    artifacts = discover_harness_artifacts(FIXTURE_ROOT)

    issues = mine_issues(traces, trajectories, artifacts, judge=LocalFallbackJudge())

    assert issues[0].metadata["diagnosis"]["calibration"]["scorer"] == (
        "structured_probabilistic_v1"
    )


def test_write_diagnosis_persists_review_artifact(tmp_path: Path) -> None:
    traces = JsonlTraceAdapter("../traces/support-agent-cancellation.jsonl").read(FIXTURE_ROOT)
    trajectories = [build_trajectory(trace) for trace in traces]
    artifacts = discover_harness_artifacts(FIXTURE_ROOT)
    issue = mine_issues(traces, trajectories, artifacts)[0]

    path = write_diagnosis(tmp_path, diagnosis_from_dict(issue.metadata["diagnosis"]))

    assert path.name == "ACTION_AUTHORIZATION_ERROR.json"
    assert "structured_probabilistic_v1" in path.read_text(encoding="utf-8")
