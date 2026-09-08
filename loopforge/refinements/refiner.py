"""Component-specific refinement pass orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from loopforge.models.issue import Issue
from loopforge.models.patch import PatchBundle
from loopforge.models.refinement import RefinementOperation
from loopforge.patching.generator import generate_patch_for_issue
from loopforge.refinements.ledger import refinement_operations_for_patch


@dataclass(frozen=True)
class ComponentRefinerPass:
    name: str
    component_type: str
    layer: str
    risk: str


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
]


def refine_issue(
    root: Path,
    issue: Issue,
    eval_ids: list[str],
    *,
    preferred_layer: str | None = None,
) -> RefinementDraft:
    passes = _ordered_passes(issue, preferred_layer)
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
) -> list[ComponentRefinerPass]:
    by_layer = {refiner_pass.layer: refiner_pass for refiner_pass in REFINER_PASSES}
    if preferred_layer:
        return [by_layer[preferred_layer]] if preferred_layer in by_layer else []

    layers = [refiner_pass.layer for refiner_pass in REFINER_PASSES]
    layers.extend(layer for layer in issue.recommended_patch_layers if layer in by_layer)
    deduped = []
    seen = set()
    for layer in layers:
        if layer in seen:
            continue
        seen.add(layer)
        deduped.append(by_layer[layer])
    return deduped
