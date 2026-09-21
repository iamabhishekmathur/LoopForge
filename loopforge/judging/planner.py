"""Plan hypothesis judge tasks for observed runs."""

from __future__ import annotations

from loopforge.models.behavior import AgentBehaviorMap
from loopforge.models.hypothesis import JudgePlan, JudgeTask
from loopforge.models.observed import ObservedAgentRun


TASK_SPECS = [
    (
        "intent_alignment",
        "Did the observed behavior plausibly address the user's intent?",
        ["user_intent", "execution_steps"],
    ),
    (
        "tool_selection",
        "Was the selected tool or agent route plausible for this request?",
        ["user_intent", "tool_calls"],
    ),
    (
        "clarification_need",
        "Did the agent likely need to ask a clarification before acting?",
        ["user_intent", "tool_calls", "execution_steps"],
    ),
    (
        "final_answer_faithfulness",
        "Did the final answer appear faithful to tool results?",
        ["final_response", "execution_steps"],
    ),
    (
        "guardrail_adherence",
        "Were relevant guardrails visible and apparently followed?",
        ["guardrail_verdict", "execution_steps"],
    ),
]


def plan_judges(run: ObservedAgentRun, behavior_map: AgentBehaviorMap) -> JudgePlan:
    available = set(run.available_evidence)
    tasks = []
    for index, (task_type, question, required) in enumerate(TASK_SPECS, start=1):
        missing = [item for item in required if item not in available]
        tasks.append(
            JudgeTask(
                task_id=f"{run.trace_id}:judge-{index}",
                task_type=task_type,
                question=question,
                required_evidence=required,
                available_evidence=[item for item in required if item in available],
                missing_evidence=missing,
                judgeable=not missing,
            )
        )
    return JudgePlan(
        plan_id=f"judge-plan-{run.trace_id}",
        trace_id=run.trace_id,
        judgeability_score=run.judgeability_score,
        tasks=tasks,
        behavior_map_id=behavior_map.map_id,
        metadata={
            "behavior_artifacts": behavior_map.artifact_count,
            "tool_catalog_size": len(behavior_map.tool_catalog),
        },
    )

