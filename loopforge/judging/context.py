"""Select trace and codebase evidence for probabilistic judges."""

from __future__ import annotations

import re
from typing import Any

from loopforge.models.behavior import AgentBehaviorMap, BehaviorContract
from loopforge.models.observed import ObservedAgentRun, ObservedStep


TOKEN_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z0-9_]{2,}")
LOW_SIGNAL_TOKENS = {
    "agent",
    "assistant",
    "context",
    "input",
    "output",
    "result",
    "run",
    "step",
    "tool",
    "user",
}


def select_relevant_contracts(
    run: ObservedAgentRun,
    behavior_map: AgentBehaviorMap,
    *,
    limit: int = 24,
) -> list[BehaviorContract]:
    """Retrieve candidate contracts; the model remains the behavior decision-maker."""

    query = " ".join(
        [run.user_intent or "", run.final_response or "", *run.tool_calls]
        + [step.name for step in run.steps]
    )
    query_tokens = _tokens(query)
    ranked: list[tuple[float, int, BehaviorContract]] = []
    for index, contract in enumerate(behavior_map.contracts):
        text = _contract_text(contract)
        contract_tokens = _tokens(text)
        overlap = query_tokens & contract_tokens
        score = sum(2.0 if "_" in token else 1.0 for token in overlap)
        lowered_query = query.lower()
        tool_name = str(contract.metadata.get("tool_name") or "").lower()
        if tool_name and tool_name in lowered_query:
            score += 8.0
        if contract.source_path.lower() in lowered_query:
            score += 5.0
        if contract.contract_type in {"system_prompt", "routing_policy", "permission_policy"}:
            score += 0.35
        ranked.append((score, -index, contract))

    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    selected = [contract for score, _, contract in ranked if score > 0][:limit]
    selected_ids = {contract.contract_id for contract in selected}

    # Preserve broad harness coverage when lexical retrieval is sparse.
    for contract_type in (
        "system_prompt",
        "routing_policy",
        "tool_definition",
        "skill",
        "permission_policy",
        "context_policy",
    ):
        if any(contract.contract_type == contract_type for contract in selected):
            continue
        fallback = next(
            (contract for contract in behavior_map.contracts if contract.contract_type == contract_type),
            None,
        )
        if fallback and fallback.contract_id not in selected_ids and len(selected) < limit:
            selected.append(fallback)
            selected_ids.add(fallback.contract_id)
    return selected


def select_trajectory_steps(
    run: ObservedAgentRun,
    *,
    limit: int = 36,
) -> list[ObservedStep]:
    """Keep trajectory boundaries plus semantically important middle events."""

    if len(run.steps) <= limit:
        return list(run.steps)
    selected_indices = set(range(min(4, len(run.steps))))
    selected_indices.update(range(max(0, len(run.steps) - 8), len(run.steps)))

    scored: list[tuple[float, int]] = []
    for index, step in enumerate(run.steps):
        text = f"{step.name} {step.step_type} {step.input_preview} {step.output_preview}".lower()
        score = 0.0
        if step.error:
            score += 10.0
        if step.step_type == "tool_call":
            score += 7.0
        if step.name in run.tool_calls:
            score += 5.0
        for marker, weight in (
            ("guardrail", 8.0),
            ("policy", 5.0),
            ("sql", 6.0),
            ("query", 3.0),
            ("summary", 5.0),
            ("answer", 5.0),
            ("clarification", 5.0),
            ("route", 3.0),
            ("permission", 6.0),
        ):
            if marker in text:
                score += weight
        if score:
            scored.append((score, index))
    for _, index in sorted(scored, key=lambda item: (item[0], item[1]), reverse=True):
        selected_indices.add(index)
        if len(selected_indices) >= limit:
            break

    if len(selected_indices) < limit:
        stride = max(1, len(run.steps) // (limit - len(selected_indices) + 1))
        selected_indices.update(range(stride, len(run.steps), stride))
    return [run.steps[index] for index in sorted(selected_indices)[:limit]]


def contract_excerpt(contract: BehaviorContract, *, max_chars: int = 1800) -> str | None:
    metadata = contract.metadata
    candidates: list[Any] = [
        metadata.get("embedding_text"),
        metadata.get("content_excerpt"),
        metadata.get("evidence"),
        metadata.get("anchors"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        text = str(candidate)
        if len(text) > max_chars:
            return text[:max_chars] + "..."
        return text
    return None


def _contract_text(contract: BehaviorContract) -> str:
    metadata = contract.metadata
    return " ".join(
        str(value)
        for value in (
            contract.contract_type,
            contract.source_path,
            contract.summary,
            metadata.get("tool_name"),
            metadata.get("embedding_text"),
            metadata.get("signals"),
            metadata.get("anchors"),
        )
        if value
    )


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in (match.group(0).lower() for match in TOKEN_PATTERN.finditer(value))
        if token not in LOW_SIGNAL_TOKENS
    }
