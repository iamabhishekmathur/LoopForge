"""Component-specific refinement pass orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from loopforge.models.issue import Issue
from loopforge.models.patch import PatchBundle
from loopforge.models.refinement import RefinementOperation
from loopforge.patching.generator import generate_patch_for_issue
from loopforge.refinements.ledger import refinement_operations_for_patch
from loopforge.refinements.model import LocalProbabilisticRefinerModel, RefinerModel


@dataclass(frozen=True)
class ComponentRefinerPass:
    name: str
    component_type: str
    layer: str
    risk: str
    score: float = 0.0
    score_rationale: str = ""


@dataclass(frozen=True)
class RefinementDraft:
    issue_id: str
    status: str
    selected_pass: str | None = None
    selected_layer: str | None = None
    patch: PatchBundle | None = None
    operations: list[RefinementOperation] = field(default_factory=list)
    abstentions: list[dict[str, str]] = field(default_factory=list)
    reason: str = ""


REFINER_PASSES = [
    ComponentRefinerPass("tool_refiner", "tool", "tool_description", "low"),
    ComponentRefinerPass("policy_refiner", "policy", "permission_policy", "high"),
    ComponentRefinerPass("prompt_refiner", "prompt", "system_prompt", "medium"),
    ComponentRefinerPass("skill_refiner", "skill", "skill", "medium"),
    ComponentRefinerPass("routing_refiner", "policy", "routing_policy", "medium"),
    ComponentRefinerPass("context_refiner", "policy", "context_policy", "medium"),
    ComponentRefinerPass("retrieval_refiner", "policy", "retrieval_policy", "medium"),
    ComponentRefinerPass("eval_refiner", "eval", "evaluator", "low"),
    ComponentRefinerPass("subagent_spec_refiner", "sub_agent", "subagent_spec", "medium"),
]


def refine_issue(
    root: Path,
    issue: Issue,
    eval_ids: list[str],
    *,
    preferred_layer: str | None = None,
    model: RefinerModel | None = None,
) -> RefinementDraft:
    passes = _ordered_passes(issue, preferred_layer, model or LocalProbabilisticRefinerModel())
    abstentions: list[dict[str, str]] = []
    for refiner_pass in passes:
        patch = generate_patch_for_issue(
            root,
            issue,
            eval_ids,
            preferred_layer=refiner_pass.layer,
        )
        if patch is None:
            abstentions.append(
                {
                    "pass": refiner_pass.name,
                    "layer": refiner_pass.layer,
                    "reason": "no grounded patch available for this component",
                }
            )
            continue

        annotated_patch = replace(
            patch,
            metadata={
                **patch.metadata,
                "component_pass": refiner_pass.name,
                "component_type": refiner_pass.component_type,
                "component_risk": refiner_pass.risk,
                "component_score": getattr(refiner_pass, "score", None),
                "component_score_rationale": getattr(refiner_pass, "score_rationale", ""),
                "ranked_component_passes": [
                    {
                        "pass": candidate.name,
                        "layer": candidate.layer,
                        "score": candidate.score,
                    }
                    for candidate in passes
                ],
                "abstained_passes": abstentions,
            },
        )
        return RefinementDraft(
            issue_id=issue.issue_id,
            status="drafted",
            selected_pass=refiner_pass.name,
            selected_layer=refiner_pass.layer,
            patch=annotated_patch,
            operations=refinement_operations_for_patch(issue, annotated_patch),
            abstentions=abstentions,
        )

    return RefinementDraft(
        issue_id=issue.issue_id,
        status="abstained",
        abstentions=abstentions,
        reason="No component refiner found a grounded, safe patch candidate.",
    )


def _ordered_passes(
    issue: Issue,
    preferred_layer: str | None,
    model: RefinerModel,
) -> list[ComponentRefinerPass]:
    by_layer = {refiner_pass.layer: refiner_pass for refiner_pass in REFINER_PASSES}
    if preferred_layer:
        if preferred_layer not in by_layer:
            return []
        base_passes = [by_layer[preferred_layer]]
    else:
        base_passes = REFINER_PASSES

    candidates = model.score_passes(
        issue,
        [
            {
                "name": refiner_pass.name,
                "component_type": refiner_pass.component_type,
                "layer": refiner_pass.layer,
                "risk": refiner_pass.risk,
            }
            for refiner_pass in base_passes
        ],
        preferred_layer=preferred_layer,
    )
    ranked = []
    for candidate in candidates:
        refiner_pass = by_layer[candidate.layer]
        ranked.append(
            ComponentRefinerPass(
                name=refiner_pass.name,
                component_type=refiner_pass.component_type,
                layer=refiner_pass.layer,
                risk=refiner_pass.risk,
                score=candidate.score,
                score_rationale=candidate.rationale,
            )
        )
    return ranked
