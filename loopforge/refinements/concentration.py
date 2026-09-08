"""Patch concentration analysis for refinement operations."""

from __future__ import annotations

from dataclasses import dataclass

from loopforge.models.patch import PatchBundle


@dataclass(frozen=True)
class PatchConcentration:
    status: str
    level: str
    max_count: int
    artifact_path: str
    messages: list[str]

    def to_suite(self) -> dict[str, object]:
        return {
            "name": "patch_concentration",
            "status": self.status,
            "score_after": 1.0 if self.status == "pass" else 0.5,
            "failed_cases": self.messages,
        }


def analyze_patch_concentration(
    patch: PatchBundle,
    operation_history: list[dict[str, object]],
    *,
    alert_count: int = 3,
) -> PatchConcentration:
    target_paths = {
        str(artifact.get("path") or "")
        for artifact in patch.target_artifacts
        if artifact.get("path")
    }
    if not target_paths:
        return PatchConcentration("pass", "low", 0, "", [])

    counts = {path: 0 for path in target_paths}
    unconfirmed_counts = {path: 0 for path in target_paths}
    for operation in operation_history:
        path = str(operation.get("artifact_path") or "")
        if path not in counts:
            continue
        counts[path] += 1
        metadata = operation.get("metadata")
        outcome = metadata.get("post_merge_outcome") if isinstance(metadata, dict) else None
        if outcome != "confirmed":
            unconfirmed_counts[path] += 1

    artifact_path, max_count = max(counts.items(), key=lambda item: item[1])
    unconfirmed_count = unconfirmed_counts.get(artifact_path, 0)
    if unconfirmed_count >= alert_count:
        return PatchConcentration(
            status="warn",
            level="high",
            max_count=unconfirmed_count,
            artifact_path=artifact_path,
            messages=[
                (
                    f"{artifact_path} has {unconfirmed_count} unconfirmed refinement "
                    "operations; consider architecture, instrumentation, or a different patch layer."
                )
            ],
        )
    return PatchConcentration("pass", "low", max_count, artifact_path, [])
