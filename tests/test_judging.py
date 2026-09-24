from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from loopforge.judging.behavior_map import build_behavior_map
from loopforge.judging.interpreter import interpret_trace
from loopforge.judging.model_judge import OpenAICompatibleHypothesisJudge
from loopforge.judging.planner import plan_judges
from loopforge.models.harness import HarnessArtifact
from loopforge.models.trace import Trace
from loopforge.traces.stitcher import stitch_traces


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


def test_interpreter_scores_full_agent_trace_as_more_judgeable() -> None:
    trace = Trace.from_dict(
        {
            "schema_version": "1",
            "trace_id": "tr_full",
            "started_at": "2026-09-21T00:00:00Z",
            "inputs": {"user_message": "What plans can I downgrade to?"},
            "outputs": {"assistant_message": "Here are the downgrade options."},
            "spans": [
                {
                    "span_id": "sp_1",
                    "type": "tool_call",
                    "name": "get_plan_options",
                    "started_at": "2026-09-21T00:00:01Z",
                    "input": {"customer_id": "hash_1"},
                    "output": {"plans": ["basic", "pro"]},
                    "side_effect_class": "read",
                }
            ],
        }
    )

    observed = interpret_trace(trace)

    assert observed.user_intent == "What plans can I downgrade to?"
    assert observed.final_response == "Here are the downgrade options."
    assert observed.tool_calls == ["get_plan_options"]
    assert observed.judgeability_score >= 0.5
    assert "user_intent" in observed.available_evidence
    assert "final_response" in observed.available_evidence


def test_interpreter_extracts_langchain_tuple_messages() -> None:
    trace = Trace.from_dict(
        {
            "schema_version": "1",
            "trace_id": "tr_langchain_tuple",
            "started_at": "2026-09-21T00:00:00Z",
            "inputs": {
                "input": [
                    ["system", "You are a citation assistant."],
                    [
                        "user",
                        "## User question\nare there other concentrations that we should be monitoring?\n\n## Steps to document\n...",
                    ],
                ]
            },
            "outputs": {"output": {"entries": [{"ref": "balance_conc"}]}},
            "spans": [
                {
                    "span_id": "sp_1",
                    "type": "llm_call",
                    "name": "ChatAnthropic",
                    "started_at": "2026-09-21T00:00:01Z",
                    "input": {},
                    "output": {},
                }
            ],
        }
    )

    observed = interpret_trace(trace)

    assert observed.user_intent == "are there other concentrations that we should be monitoring?"
    assert observed.final_response is not None
    assert "balance_conc" in observed.final_response
    assert "user_intent" in observed.available_evidence
    assert "final_response" in observed.available_evidence


def test_interpreter_extracts_langchain_human_messages() -> None:
    trace = Trace.from_dict(
        {
            "schema_version": "1",
            "trace_id": "tr_langchain_human",
            "started_at": "2026-09-21T00:00:00Z",
            "inputs": {"input": {"reasoning": "tool result"}},
            "outputs": {"output": {"reasoning": "classified as high risk", "risk_level": "high"}},
            "spans": [
                {
                    "span_id": "sp_1",
                    "type": "router",
                    "name": "sql_gen_tool_dispatch",
                    "started_at": "2026-09-21T00:00:01Z",
                    "input": {
                        "input": [
                            {
                                "id": ["langchain", "schema", "messages", "HumanMessage"],
                                "kwargs": {
                                    "content": "Generate SQL.\n\nAnalytical plan request:\nwhat branches/centers have most at risk dollars and clients?\n\n"
                                },
                            }
                        ]
                    },
                    "output": {},
                }
            ],
        }
    )

    observed = interpret_trace(trace)

    assert observed.user_intent == "what branches/centers have most at risk dollars and clients?"
    assert observed.final_response is not None
    assert "classified as high risk" in observed.final_response


def test_interpreter_prefers_real_user_request_over_internal_human_prompt() -> None:
    trace = Trace.from_dict(
        {
            "schema_version": "1",
            "trace_id": "tr_langchain_internal_prompt",
            "started_at": "2026-09-21T00:00:00Z",
            "inputs": {},
            "outputs": {"output": {"reasoning": "risk is concentrated in three branches"}},
            "spans": [
                {
                    "span_id": "sp_1",
                    "type": "llm_call",
                    "name": "ChatPromptTemplate",
                    "started_at": "2026-09-21T00:00:01Z",
                    "input": {
                        "messages": [
                            {
                                "id": ["langchain", "schema", "messages", "HumanMessage"],
                                "kwargs": {
                                    "content": (
                                        "## BEHAVIOURAL LAYER\n"
                                        "GLOBAL CRITICAL RULES\n"
                                        "You are an expert analyst. Follow SQL Generation Principles."
                                    )
                                },
                            },
                            {
                                "id": ["langchain", "schema", "messages", "HumanMessage"],
                                "kwargs": {
                                    "content": (
                                        "Generate SQL.\n\nAnalytical plan request:\n"
                                        "what branches/centers have most at risk dollars and clients?\n\n"
                                    )
                                },
                            },
                        ]
                    },
                    "output": {},
                }
            ],
        }
    )

    observed = interpret_trace(trace)

    assert observed.user_intent == "what branches/centers have most at risk dollars and clients?"
    assert "BEHAVIOURAL LAYER" not in observed.user_intent


def test_interpreter_prefers_explicit_state_user_query_over_internal_prompt() -> None:
    trace = Trace.from_dict(
        {
            "schema_version": "1",
            "trace_id": "tr_state_user_query",
            "started_at": "2026-09-21T00:00:00Z",
            "inputs": {
                "input": [
                    {
                        "role": "user",
                        "content": "You will be provided SQL Query, Schema, and SQL Response.",
                    }
                ]
            },
            "outputs": {"output": {"summary": "Customer 302314 has one active account."}},
            "spans": [
                {
                    "span_id": "sp_1",
                    "type": "router",
                    "name": "post_execution_node",
                    "started_at": "2026-09-21T00:00:01Z",
                    "input": {
                        "user_query": "list all the accounts for customer id 302314",
                        "artifact_store": {"artifacts": []},
                    },
                    "output": {},
                }
            ],
        }
    )

    observed = interpret_trace(trace)

    assert observed.user_intent == "list all the accounts for customer id 302314"
    assert "SQL Query" not in observed.user_intent


def test_interpreter_does_not_treat_tool_use_as_final_response() -> None:
    trace = Trace.from_dict(
        {
            "schema_version": "1",
            "trace_id": "tr_tool_use_final",
            "started_at": "2026-09-21T00:00:00Z",
            "inputs": {"user_message": "Which branches are profitable?"},
            "outputs": {
                "output": {
                    "type": "ai",
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "submit_reflection",
                            "input": {"issues": [], "retry": False},
                        }
                    ],
                }
            },
            "spans": [
                {
                    "span_id": "sp_1",
                    "type": "llm_call",
                    "name": "ChatAnthropic",
                    "started_at": "2026-09-21T00:00:01Z",
                    "input": {},
                    "output": {
                        "output": {
                            "type": "ai",
                            "content": (
                                "This report ranks branch profitability using deposit income proxy. "
                                "The top branches are profitable while several admin centers are not."
                            ),
                        }
                    },
                },
                {
                    "span_id": "sp_2",
                    "type": "router",
                    "name": "post_execution_node",
                    "started_at": "2026-09-21T00:00:02Z",
                    "input": {},
                    "output": {
                        "output": {
                            "goto": "__end__",
                            "update": {"artifact_store": {"artifacts": []}},
                        }
                    },
                },
            ],
        }
    )

    observed = interpret_trace(trace)

    assert observed.final_response is not None
    assert "deposit income proxy" in observed.final_response
    assert "submit_reflection" not in observed.final_response
    assert "artifact_store" not in observed.final_response


def test_interpreter_extracts_summary_from_tool_use_response() -> None:
    trace = Trace.from_dict(
        {
            "schema_version": "1",
            "trace_id": "tr_tool_use_summary",
            "started_at": "2026-09-21T00:00:00Z",
            "inputs": {"user_message": "Which branches are profitable?"},
            "outputs": {
                "output": {
                    "type": "ai",
                    "content": [
                        {
                            "caller": {"type": "direct"},
                            "type": "tool_use",
                            "name": "submit_narration",
                            "input": {
                                "textToSQLSummary": (
                                    "This report covers branch-level deposit performance and "
                                    "identifies profitable branches using deposit income proxy."
                                )
                            },
                        }
                    ],
                }
            },
            "spans": [
                {
                    "span_id": "sp_1",
                    "type": "llm_call",
                    "name": "ChatAnthropic",
                    "started_at": "2026-09-21T00:00:01Z",
                    "input": {},
                    "output": {},
                }
            ],
        }
    )

    observed = interpret_trace(trace)

    assert observed.final_response is not None
    assert observed.final_response.startswith("This report covers branch-level")
    assert "submit_narration" not in observed.final_response


def test_judge_planner_names_missing_evidence_for_partial_trace() -> None:
    trace = Trace.from_dict(
        {
            "schema_version": "1",
            "trace_id": "tr_sql_only",
            "started_at": "2026-09-21T00:00:00Z",
            "inputs": {"db_query": "select count(*) from orders"},
            "outputs": {"rowsCount": 1},
            "spans": [
                {
                    "span_id": "sp_1",
                    "type": "router",
                    "name": "sql_execution",
                    "started_at": "2026-09-21T00:00:01Z",
                    "input": {"db_query": "select count(*) from orders"},
                    "output": {"rowsCount": 1},
                }
            ],
        }
    )
    artifact = HarnessArtifact(
        artifact_id="system_1",
        artifact_type="system_prompt",
        path="harness/system.md",
        confidence=0.9,
        last_indexed_at="2026-09-21T00:00:00Z",
        summary="System-level agent instructions.",
    )
    behavior_map = build_behavior_map([artifact])

    observed = interpret_trace(trace)
    plan = plan_judges(observed, behavior_map)

    assert observed.user_intent is None
    assert "user_intent" in observed.missing_evidence
    assert "final_response" in observed.missing_evidence
    assert any(not task.judgeable for task in plan.tasks)


def test_stitcher_inherits_nearby_turn_context_for_runtime_trace() -> None:
    turn_trace = Trace.from_dict(
        {
            "schema_version": "1",
            "trace_id": "tr_turn",
            "session_id": "session-1",
            "started_at": "2026-09-21T00:00:10Z",
            "inputs": {"user_query": "list all accounts for customer 302314"},
            "outputs": {"assistant_message": "Customer 302314 has one active account."},
            "spans": [
                {
                    "span_id": "turn_1",
                    "type": "router",
                    "name": "post_execution_node",
                    "started_at": "2026-09-21T00:00:11Z",
                    "input": {"current_turn_id": "turn-1"},
                    "output": {},
                }
            ],
            "metadata": {"source_id": "prod", "source_type": "langsmith"},
        }
    )
    runtime_trace = Trace.from_dict(
        {
            "schema_version": "1",
            "trace_id": "tr_runtime",
            "session_id": "session-1",
            "started_at": "2026-09-21T00:00:22Z",
            "inputs": {"db_query": "select * from accounts"},
            "outputs": {"rowsCount": 1},
            "spans": [
                {
                    "span_id": "sql_1",
                    "type": "router",
                    "name": "sql_execution",
                    "started_at": "2026-09-21T00:00:22Z",
                    "input": {"conversation_id": "conversation-1", "db_query": "select * from accounts"},
                    "output": {"rowsCount": 1},
                }
            ],
            "metadata": {"source_id": "prod", "source_type": "langsmith"},
        }
    )

    stitched = {trace.trace_id: trace for trace in stitch_traces([runtime_trace, turn_trace])}
    observed = interpret_trace(stitched["tr_runtime"])

    assert observed.user_intent == "list all accounts for customer 302314"
    assert observed.final_response == "Customer 302314 has one active account."
    assert "user_intent" in observed.available_evidence
    assert "final_response" in observed.available_evidence
    assert "user_intent" not in observed.missing_evidence
    assert stitched["tr_runtime"].metadata["stitching"]["method"] == "same_session_temporal"


def test_stitcher_does_not_inherit_stale_session_context() -> None:
    old_turn = Trace.from_dict(
        {
            "schema_version": "1",
            "trace_id": "tr_old_turn",
            "session_id": "session-1",
            "started_at": "2026-09-21T00:00:00Z",
            "inputs": {"user_query": "old question"},
            "outputs": {"assistant_message": "old answer"},
            "spans": [
                {
                    "span_id": "old_1",
                    "type": "router",
                    "name": "agent",
                    "started_at": "2026-09-21T00:00:00Z",
                    "input": {},
                    "output": {},
                }
            ],
            "metadata": {"source_id": "prod", "source_type": "langsmith"},
        }
    )
    runtime = Trace.from_dict(
        {
            "schema_version": "1",
            "trace_id": "tr_late_runtime",
            "session_id": "session-1",
            "started_at": "2026-09-21T01:00:00Z",
            "inputs": {"db_query": "select 1"},
            "outputs": {"rowsCount": 1},
            "spans": [
                {
                    "span_id": "sql_1",
                    "type": "router",
                    "name": "sql_execution",
                    "started_at": "2026-09-21T01:00:00Z",
                    "input": {"db_query": "select 1"},
                    "output": {"rowsCount": 1},
                }
            ],
            "metadata": {"source_id": "prod", "source_type": "langsmith"},
        }
    )

    stitched = {trace.trace_id: trace for trace in stitch_traces([runtime, old_turn])}
    observed = interpret_trace(stitched["tr_late_runtime"])

    assert observed.user_intent is None
    assert "stitching" not in stitched["tr_late_runtime"].metadata


def test_judge_cli_persists_hypothesis_findings(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "harness").mkdir()
    (project / "traces").mkdir()
    (project / "harness" / "system.md").write_text(
        "You are a support agent. Use tools only when they answer the user's request.",
        encoding="utf-8",
    )
    trace = {
        "schema_version": "1",
        "trace_id": "tr_partial",
        "started_at": "2026-09-21T00:00:00Z",
        "inputs": {"db_query": "select count(*) from orders"},
        "outputs": {"rowsCount": 1},
        "spans": [
            {
                "span_id": "sp_1",
                "type": "router",
                "name": "sql_execution",
                "started_at": "2026-09-21T00:00:01Z",
                "input": {"db_query": "select count(*) from orders"},
                "output": {"rowsCount": 1},
            }
        ],
    }
    (project / "traces" / "sample.jsonl").write_text(json.dumps(trace) + "\n", encoding="utf-8")

    init = run_loopforge(["init", "--trace-path", "traces/*.jsonl"], project)
    shadow = run_loopforge(["shadow"], project)
    judge = run_loopforge(["judge", "run"], project)
    findings = run_loopforge(["judge", "list"], project)

    assert init.returncode == 0, init.stderr
    assert shadow.returncode == 0, shadow.stderr
    assert judge.returncode == 0, judge.stderr
    assert "findings: 1" in judge.stdout
    assert findings.returncode == 0, findings.stderr
    assert "insufficient_trace_coverage" in findings.stdout

    trace["inputs"] = {"user_message": "What plans can I downgrade to?"}
    trace["outputs"] = {"assistant_message": "You can downgrade to Basic."}
    trace["spans"] = [
        {
            "span_id": "sp_1",
            "type": "tool_call",
            "name": "downgrade_plan_lookup",
            "started_at": "2026-09-21T00:00:01Z",
            "input": {"user_message": "What plans can I downgrade to?"},
            "output": {"plans": ["Basic"], "response": "You can downgrade to Basic."},
        }
    ]
    (project / "traces" / "sample.jsonl").write_text(json.dumps(trace) + "\n", encoding="utf-8")

    shadow = run_loopforge(["shadow"], project)
    judge = run_loopforge(["judge", "run"], project)
    findings = run_loopforge(["judge", "list"], project)

    assert shadow.returncode == 0, shadow.stderr
    assert judge.returncode == 0, judge.stderr
    assert "findings: 0" in judge.stdout
    assert findings.returncode == 0, findings.stderr
    assert "insufficient_trace_coverage" not in findings.stdout


def test_recorded_hypothesis_judge_replaces_weak_local_intent_gap(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "harness").mkdir()
    (project / "traces").mkdir()
    (project / "harness" / "router.md").write_text(
        "Cancellation requests must route to the retention agent before cancellation tools.",
        encoding="utf-8",
    )
    trace = {
        "schema_version": "1",
        "trace_id": "tr_route_gap",
        "started_at": "2026-09-21T00:00:00Z",
        "inputs": {"user_message": "Can you help me cancel my account?"},
        "outputs": {"assistant_message": "I checked the weather forecast."},
        "spans": [
            {
                "span_id": "sp_1",
                "type": "tool_call",
                "name": "weather_lookup",
                "started_at": "2026-09-21T00:00:01Z",
                "input": {"city": "Toronto"},
                "output": {"forecast": "sunny"},
            }
        ],
    }
    judge_payload = {
        "findings": [
            {
                "finding_type": "tool_selection_mismatch",
                "title": "Cancellation request routed to unrelated tool",
                "hypothesis": "The user asked for cancellation help, but the trace used weather_lookup.",
                "severity": "medium",
                "confidence": 0.86,
                "supporting_trace_evidence": [
                    {"kind": "user_intent", "value": "Can you help me cancel my account?"},
                    {"kind": "tool_calls", "value": ["weather_lookup"]},
                ],
                "supporting_codebase_evidence": [
                    {
                        "contract_type": "routing_policy",
                        "source_path": "harness/router.md",
                        "summary": "Cancellation requests must route to retention.",
                        "confidence": 0.9,
                    }
                ],
                "missing_evidence": [],
                "recommended_next_action": "Inspect router policy before patching.",
                "expected_behavior": "Route cancellation requests to retention.",
                "actual_behavior": "Called weather_lookup.",
            }
        ]
    }
    (project / "traces" / "sample.jsonl").write_text(json.dumps(trace) + "\n", encoding="utf-8")
    (project / "judge.json").write_text(json.dumps(judge_payload), encoding="utf-8")

    init = run_loopforge(["init", "--trace-path", "traces/*.jsonl"], project)
    config_path = project / "loopforge.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + "\nanalysis:\n"
        + "  hypothesis_judge: json_file\n"
        + "  hypothesis_judge_path: judge.json\n",
        encoding="utf-8",
    )
    shadow = run_loopforge(["shadow"], project)
    judge = run_loopforge(["judge", "run"], project)
    findings = run_loopforge(["judge", "list"], project)

    assert init.returncode == 0, init.stderr
    assert shadow.returncode == 0, shadow.stderr
    assert judge.returncode == 0, judge.stderr
    assert "findings: 1" in judge.stdout
    assert findings.returncode == 0, findings.stderr
    assert "tool_selection_mismatch" in findings.stdout
    assert "possible_intent_mismatch" not in findings.stdout


def test_live_hypothesis_judge_requires_external_llm_opt_in(tmp_path: Path) -> None:
    (tmp_path / "loopforge.yaml").write_text(
        "version: 1\n"
        "analysis:\n"
        "  hypothesis_judge: openai_compatible\n",
        encoding="utf-8",
    )

    from loopforge.config import configured_hypothesis_judge

    try:
        configured_hypothesis_judge(tmp_path)
    except ValueError as exc:
        assert "external_llm_allowed" in str(exc)
    else:
        raise AssertionError("expected external LLM opt-in failure")


def test_hypothesis_llm_payload_includes_trace_plan_and_codebase_context() -> None:
    trace = Trace.from_dict(
        {
            "schema_version": "1",
            "trace_id": "tr_payload",
            "started_at": "2026-09-21T00:00:00Z",
            "inputs": {"user_message": "Can you cancel my account?"},
            "outputs": {"assistant_message": "I checked the weather."},
            "spans": [
                {
                    "span_id": "sp_1",
                    "type": "tool_call",
                    "name": "weather_lookup",
                    "started_at": "2026-09-21T00:00:01Z",
                    "input": {"city": "Toronto"},
                    "output": {"forecast": "sunny"},
                }
            ],
        }
    )
    artifact = HarnessArtifact(
        artifact_id="router_1",
        artifact_type="routing_policy",
        path="harness/router.md",
        confidence=0.9,
        last_indexed_at="2026-09-21T00:00:00Z",
        summary="Cancellation requests must route to retention.",
    )
    behavior_map = build_behavior_map([artifact])
    observed = interpret_trace(trace)
    plan = plan_judges(observed, behavior_map)
    judge = OpenAICompatibleHypothesisJudge(
        endpoint="https://example.invalid/v1/chat/completions",
        model="test-model",
    )

    payload = json.loads(judge._user_payload(observed, plan, behavior_map, []))

    assert "No ground truth is available" in payload["task"]
    assert payload["observed_run"]["user_intent"] == "Can you cancel my account?"
    assert payload["observed_run"]["tool_calls"] == ["weather_lookup"]
    assert payload["judge_plan"]["trace_id"] == "tr_payload"
    assert payload["behavior_map"]["contracts"][0]["source_path"] == "harness/router.md"
    assert "findings" in payload["output_contract"]
