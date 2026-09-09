from __future__ import annotations

import json
import shutil
from pathlib import Path

from loopforge.adapters.jsonl import JsonlTraceAdapter
from loopforge.analysis.authorization import diagnosis_from_dict
from loopforge.analysis.judge import (
    JsonFileJudge,
    LocalFallbackJudge,
    OpenAICompatibleJudge,
    write_diagnosis,
)
from loopforge.config import configured_issue_judge
from loopforge.discovery.scanner import discover_harness_artifacts
from loopforge.issues.miner import mine_issues
from loopforge.shadow.runner import run_shadow_pipeline
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


def test_configured_json_file_judge_runs_inside_shadow_pipeline(tmp_path: Path) -> None:
    fixture_root = tmp_path / "fixtures"
    shutil.copytree(REPO_ROOT / "fixtures", fixture_root)
    project_root = fixture_root / "support-agent"
    judge_path = project_root / "issue-judge.json"
    judge_path.write_text(
        (REPO_ROOT / "tests" / "fixtures" / "model-diagnosis.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    config_text = (project_root / "loopforge.yaml").read_text(encoding="utf-8")
    (project_root / "loopforge.yaml").write_text(
        config_text
        + "\nanalysis:\n"
        + "  issue_judge: json_file\n"
        + "  issue_judge_path: issue-judge.json\n",
        encoding="utf-8",
    )

    result = run_shadow_pipeline(project_root, "24h")

    assert result.issue_count == 1
    analysis = json.loads(
        (project_root / ".loopforge" / "analysis" / "ACTION_AUTHORIZATION_ERROR.json").read_text(
            encoding="utf-8"
        )
    )
    assert analysis["calibration"]["judge"] == "json_file"
    assert analysis["calibration"]["scorer"] == "model_judge_v1"


def test_openai_compatible_judge_payload_includes_codebase_flow_context() -> None:
    traces = JsonlTraceAdapter("../traces/support-agent-cancellation.jsonl").read(FIXTURE_ROOT)
    trajectories = [build_trajectory(trace) for trace in traces]
    artifacts = discover_harness_artifacts(FIXTURE_ROOT)
    fallback = diagnosis_from_dict(mine_issues(traces, trajectories, artifacts)[0].metadata["diagnosis"])
    judge = OpenAICompatibleJudge(
        endpoint="https://example.invalid/v1/chat/completions",
        model="test-model",
    )

    payload = json.loads(judge._user_payload(traces, trajectories, artifacts, fallback))

    assert "what should have happened" in payload["task"]
    assert "agent_flow_context" in payload
    assert "harness_artifacts" in payload
    assert "expected_behavior" in payload["output_contract"]
    assert "behavior_gaps" in payload["output_contract"]
    assert "violated_contracts" in payload["output_contract"]
    assert "cancel_subscription" in payload["agent_flow_context"]["observed_tools"]


def test_configured_live_judge_requires_external_llm_opt_in(tmp_path: Path) -> None:
    (tmp_path / "loopforge.yaml").write_text(
        "version: 1\n"
        "analysis:\n"
        "  issue_judge: openai_compatible\n",
        encoding="utf-8",
    )

    try:
        configured_issue_judge(tmp_path)
    except ValueError as exc:
        assert "external_llm_allowed" in str(exc)
    else:
        raise AssertionError("expected external LLM opt-in failure")


def test_openai_compatible_judge_parses_chat_json_response() -> None:
    traces = JsonlTraceAdapter("../traces/support-agent-cancellation.jsonl").read(FIXTURE_ROOT)
    trajectories = [build_trajectory(trace) for trace in traces]
    artifacts = discover_harness_artifacts(FIXTURE_ROOT)
    fallback = mine_issues(traces, trajectories, artifacts)[0].metadata["diagnosis"]
    judge = OpenAICompatibleJudge(
        endpoint="https://example.invalid/v1/chat/completions",
        model="test-model",
    )
    payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "ontology_id": "ACTION_AUTHORIZATION_ERROR",
                            "confidence": 0.88,
                            "severity": "high",
                            "trace_observability": "medium",
                            "evidence_trace_ids": ["tr_fail_001"],
                            "implicated_tools": ["cancel_subscription"],
                            "recommended_patch_layers": ["tool_description", "eval"],
                            "root_cause_hypotheses": [
                                {
                                    "label": "model_observed_missing_confirmation",
                                    "confidence": 0.88,
                                    "explanation": "A model judge observed missing confirmation.",
                                    "evidence": ["tr_fail_001"],
                                }
                            ],
                            "expected_behavior": "The agent should ask for confirmation.",
                            "observed_behavior": "The agent called the cancellation tool immediately.",
                            "behavior_gaps": [
                                {
                                    "label": "confirmation_gap",
                                    "confidence": 0.88,
                                    "expected": "confirmation before cancellation",
                                    "observed": "cancellation before confirmation",
                                    "evidence": ["tr_fail_001"],
                                }
                            ],
                            "violated_contracts": [
                                {
                                    "contract_type": "tool_contract",
                                    "label": "requires_confirmation_before_tool",
                                    "confidence": 0.88,
                                }
                            ],
                            "agent_flow_context": {
                                "implicated_agents": ["support_agent"],
                                "observed_flow": "message -> tool_call",
                            },
                            "calibration": {
                                "scorer": "model_judge_v1",
                                "threshold": 0.7,
                                "observable_from_traces": True,
                            },
                        }
                    )
                }
            }
        ]
    }

    from loopforge.analysis.judge import _diagnosis_from_judge_payload, _extract_chat_json

    diagnosis = _diagnosis_from_judge_payload(
        _extract_chat_json(payload),
        diagnosis_from_dict(fallback),
        judge_name="openai_compatible",
        extra_calibration={"model": judge.model},
    )

    assert diagnosis is not None
    assert diagnosis.confidence == 0.88
    assert diagnosis.calibration["judge"] == "openai_compatible"
    assert diagnosis.calibration["model"] == "test-model"
    assert diagnosis.trace_scores
    assert diagnosis.expected_behavior == "The agent should ask for confirmation."
    assert diagnosis.behavior_gaps[0]["label"] == "confirmation_gap"
    assert diagnosis.violated_contracts[0]["contract_type"] == "tool_contract"
