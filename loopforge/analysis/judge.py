"""Provider-neutral model diagnosis interface."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Protocol

from loopforge.analysis.authorization import FailureDiagnosis, diagnosis_from_dict
from loopforge.models.harness import HarnessArtifact
from loopforge.models.trace import Trace
from loopforge.models.trajectory import TraceTrajectory
from loopforge.paths import LOCAL_DIR


class DiagnosisJudge(Protocol):
    def diagnose(
        self,
        traces: list[Trace],
        trajectories: list[TraceTrajectory],
        artifacts: list[HarnessArtifact],
        fallback: FailureDiagnosis | None,
    ) -> FailureDiagnosis | None:
        ...


@dataclass(frozen=True)
class LocalFallbackJudge:
    """Judge that returns the structured diagnosis unchanged."""

    def diagnose(
        self,
        traces: list[Trace],
        trajectories: list[TraceTrajectory],
        artifacts: list[HarnessArtifact],
        fallback: FailureDiagnosis | None,
    ) -> FailureDiagnosis | None:
        return fallback


@dataclass(frozen=True)
class JsonFileJudge:
    """Offline model-judge stand-in that reads a recorded diagnosis JSON file."""

    path: Path

    def diagnose(
        self,
        traces: list[Trace],
        trajectories: list[TraceTrajectory],
        artifacts: list[HarnessArtifact],
        fallback: FailureDiagnosis | None,
    ) -> FailureDiagnosis | None:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        diagnosis = diagnosis_from_dict({**payload, "trace_scores": payload.get("trace_scores") or []})
        return FailureDiagnosis(
            **{
                **diagnosis.__dict__,
                "trace_scores": diagnosis.trace_scores or (fallback.trace_scores if fallback else []),
                "calibration": {**diagnosis.calibration, "judge": "json_file"},
            }
        )


def write_diagnosis(root: Path, diagnosis: FailureDiagnosis) -> Path:
    analysis_dir = root / LOCAL_DIR / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    path = analysis_dir / f"{diagnosis.ontology_id}.json"
    path.write_text(json.dumps(diagnosis.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return path
