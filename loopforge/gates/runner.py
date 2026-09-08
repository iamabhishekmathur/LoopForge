"""Run local acceptance gates for patch bundles."""

from __future__ import annotations

import json
from pathlib import Path

from loopforge.models.patch import GateReport, PatchBundle
from loopforge.paths import LOCAL_DIR
from loopforge.refinements.concentration import analyze_patch_concentration
from loopforge.replay.runner import ReplayReport, run_replay


def run_gates(
    patch: PatchBundle,
    issue: dict[str, object],
    evals: list[dict[str, object]],
    validations: list[dict[str, object]],
    replay_report: ReplayReport | None = None,
    operation_history: list[dict[str, object]] | None = None,
) -> GateReport:
    replay_report = replay_report or run_replay(patch, issue, evals)
    concentration = analyze_patch_concentration(patch, operation_history or [])
    suites = [
        _scope_suite(patch),
        _grounding_suite(patch, issue),
        _artifact_fingerprint_suite(patch),
        _diagnosis_confidence_suite(issue),
        _eval_coverage_suite(patch, evals),
        _evaluator_validation_suite(validations),
        _replay_sandbox_suite(patch, replay_report),
        concentration.to_suite(),
    ]
    rejected = any(suite["status"] in {"reject", "error"} for suite in suites)
    warned = any(suite["status"] == "warn" for suite in suites)
    status = "reject" if rejected else "warn" if warned else "pass"
    recommendation = "merge_after_human_review" if status in {"pass", "warn"} else "revise"
    return GateReport(
        gate_report_id=f"GATE-{patch.patch_id}",
        patch_id=patch.patch_id,
        status=status,
        recommendation=recommendation,
        target_issue={
            "fixed_cases": len(issue.get("evidence_trace_ids", [])),
            "total_cases": len(issue.get("evidence_trace_ids", [])),
            "score_before": 0.0,
            "score_after": 1.0 if status == "pass" else 0.0,
        },
        suites=suites,
        trust={
            "autonomy_level": 1,
            "runtime_manifest_coverage": _runtime_manifest_coverage(patch),
            "artifact_grounding_confidence": _min_artifact_confidence(patch),
            "diagnosis_confidence": _diagnosis_confidence(issue),
            "recommendation_quality_level": "gated_patch"
            if status in {"pass", "warn"}
            else "patch_candidate",
            "replay_sandbox": replay_report.status,
            "replay_id": replay_report.replay_id,
            "patch_concentration": concentration.level,
        },
        metadata={
            "ai_drafted": True,
            "requires_human_approval": True,
            "behavior_patch": True,
        },
    )


def write_gate_report(root: Path, report: GateReport) -> Path:
    report_dir = root / LOCAL_DIR / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"{report.gate_report_id}.json"
    path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return path


def _scope_suite(patch: PatchBundle) -> dict[str, object]:
    allowed = all(
        str(artifact.get("path", "")).startswith(("harness/", "evals/"))
        for artifact in patch.target_artifacts
    )
    return {
        "name": "patch_scope",
        "status": "pass" if allowed else "reject",
        "score_after": 1.0 if allowed else 0.0,
        "failed_cases": [] if allowed else ["target outside harness/evals allowlist"],
    }


def _grounding_suite(patch: PatchBundle, issue: dict[str, object]) -> dict[str, object]:
    issue_artifact_paths = {
        str(artifact.get("path"))
        for artifact in issue.get("metadata", {}).get("implicated_artifacts", [])
        if isinstance(artifact, dict)
    }
    patch_paths = {str(artifact.get("path")) for artifact in patch.target_artifacts}
    grounded = bool(issue_artifact_paths.intersection(patch_paths))
    return {
        "name": "codebase_grounding",
        "status": "pass" if grounded else "reject",
        "score_after": 1.0 if grounded else 0.0,
        "failed_cases": [] if grounded else ["patch target not linked to issue evidence"],
    }


def _eval_coverage_suite(patch: PatchBundle, evals: list[dict[str, object]]) -> dict[str, object]:
    eval_ids = {str(eval_example["eval_id"]) for eval_example in evals}
    covered = bool(set(patch.new_eval_ids).intersection(eval_ids))
    return {
        "name": "eval_coverage",
        "status": "pass" if covered else "reject",
        "score_after": 1.0 if covered else 0.0,
        "failed_cases": [] if covered else ["patch does not reference generated eval coverage"],
    }


def _artifact_fingerprint_suite(patch: PatchBundle) -> dict[str, object]:
    missing = [
        str(artifact.get("path"))
        for artifact in patch.target_artifacts
        if not artifact.get("sha256")
    ]
    passed = not missing
    return {
        "name": "artifact_fingerprint",
        "status": "pass" if passed else "reject",
        "score_after": 1.0 if passed else 0.0,
        "failed_cases": [] if passed else missing,
    }


def _diagnosis_confidence_suite(issue: dict[str, object]) -> dict[str, object]:
    confidence = _diagnosis_confidence(issue)
    passed = confidence >= 0.70
    return {
        "name": "diagnosis_confidence",
        "status": "pass" if passed else "reject",
        "score_after": confidence,
        "failed_cases": [] if passed else [f"diagnosis confidence below threshold: {confidence}"],
    }


def _evaluator_validation_suite(validations: list[dict[str, object]]) -> dict[str, object]:
    eligible = any(validation.get("blocking_gate_eligible") is True for validation in validations)
    return {
        "name": "evaluator_validation",
        "status": "pass" if eligible else "reject",
        "score_after": 1.0 if eligible else 0.0,
        "failed_cases": [] if eligible else ["no blocking-eligible evaluator validation record"],
    }


def _replay_sandbox_suite(patch: PatchBundle, replay_report: ReplayReport) -> dict[str, object]:
    risky = any(
        artifact.get("artifact_type") == "permission_policy"
        for artifact in patch.target_artifacts
    )
    passed = replay_report.status == "pass" and (not risky or replay_report.passed_cases > 0)
    return {
        "name": "replay_sandbox",
        "status": "pass" if passed else "reject",
        "score_after": 1.0 if passed else 0.0,
        "failed_cases": []
        if passed
        else [f"replay report did not pass: {replay_report.replay_id}"],
    }


def _min_artifact_confidence(patch: PatchBundle) -> float:
    if not patch.target_artifacts:
        return 0.0
    return round(min(float(artifact.get("confidence") or 0.0) for artifact in patch.target_artifacts), 4)


def _runtime_manifest_coverage(patch: PatchBundle) -> float:
    if not patch.target_artifacts:
        return 0.0
    covered = sum(1 for artifact in patch.target_artifacts if artifact.get("sha256"))
    return round(covered / len(patch.target_artifacts), 4)


def _diagnosis_confidence(issue: dict[str, object]) -> float:
    metadata = issue.get("metadata", {})
    if isinstance(metadata, dict):
        diagnosis = metadata.get("diagnosis", {})
        if isinstance(diagnosis, dict) and "confidence" in diagnosis:
            return float(diagnosis["confidence"])
    return float(issue.get("confidence") or 0.0)
