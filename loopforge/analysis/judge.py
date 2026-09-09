"""Provider-neutral model diagnosis interface."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Protocol
from urllib.request import Request, urlopen

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
        return _diagnosis_from_judge_payload(payload, fallback, judge_name="json_file")


@dataclass(frozen=True)
class OpenAICompatibleJudge:
    """LLM-as-judge implementation using an OpenAI-compatible chat endpoint."""

    endpoint: str
    model: str
    api_key_env: str = "OPENAI_API_KEY"
    timeout_seconds: float = 30.0
    max_payload_chars: int = 60000

    def diagnose(
        self,
        traces: list[Trace],
        trajectories: list[TraceTrajectory],
        artifacts: list[HarnessArtifact],
        fallback: FailureDiagnosis | None,
    ) -> FailureDiagnosis | None:
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise ValueError(f"missing API key environment variable: {self.api_key_env}")

        body = {
            "model": self.model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": ISSUE_JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": self._user_payload(traces, trajectories, artifacts, fallback)},
            ],
        }
        request = Request(
            self.endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise ValueError(f"issue judge request failed: {exc}") from exc

        judge_payload = _extract_chat_json(response_payload)
        return _diagnosis_from_judge_payload(
            judge_payload,
            fallback,
            judge_name="openai_compatible",
            extra_calibration={"model": self.model, "endpoint": self.endpoint},
        )

    def _user_payload(
        self,
        traces: list[Trace],
        trajectories: list[TraceTrajectory],
        artifacts: list[HarnessArtifact],
        fallback: FailureDiagnosis | None,
    ) -> str:
        payload = {
            "task": "Identify one recurring agent-harness issue from these traces, or abstain.",
            "output_contract": ISSUE_JUDGE_OUTPUT_CONTRACT,
            "fallback_diagnosis": fallback.to_dict() if fallback else None,
            "traces": [_compact_trace(trace) for trace in traces],
            "trajectories": [trajectory.to_dict() for trajectory in trajectories],
            "harness_artifacts": [_compact_artifact(artifact) for artifact in artifacts],
        }
        text = json.dumps(payload, indent=2, sort_keys=True)
        if len(text) <= self.max_payload_chars:
            return text
        truncated = {
            **payload,
            "traces": [_compact_trace(trace, max_spans=4) for trace in traces[:25]],
            "trajectories": [trajectory.to_dict() for trajectory in trajectories[:25]],
            "harness_artifacts": [_compact_artifact(artifact) for artifact in artifacts[:40]],
            "truncation": {
                "reason": "payload exceeded max_payload_chars",
                "max_payload_chars": self.max_payload_chars,
            },
        }
        return json.dumps(truncated, indent=2, sort_keys=True)[: self.max_payload_chars]


ISSUE_JUDGE_SYSTEM_PROMPT = """You are LoopForge's issue-discovery judge for AI agent traces.

Review trace clusters and harness artifacts probabilistically. Identify a recurring issue only when the evidence is strong enough for a skeptical agent engineer to investigate. Prefer abstaining over inventing a problem.

Return one JSON object. Do not include Markdown. Use the provided output contract exactly. Include counterevidence and false-positive risks in calibration when relevant. Never propose code changes directly; only diagnose the issue and likely harness layers.
"""


ISSUE_JUDGE_OUTPUT_CONTRACT = {
    "abstain": "boolean optional; true when evidence is too weak",
    "ontology_id": "string; e.g. ACTION_AUTHORIZATION_ERROR",
    "confidence": "number from 0 to 1",
    "severity": "low|medium|high",
    "trace_observability": "low|medium|high",
    "evidence_trace_ids": "array of trace ids",
    "implicated_tools": "array of tool names",
    "recommended_patch_layers": "array such as permission_policy, tool_description, system_prompt, skill, routing_policy, context_policy, eval",
    "root_cause_hypotheses": "array of objects with label, confidence, explanation, evidence",
    "calibration": "object with scorer, threshold, observable_from_traces, false_positive_risks",
}


def write_diagnosis(root: Path, diagnosis: FailureDiagnosis) -> Path:
    analysis_dir = root / LOCAL_DIR / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    path = analysis_dir / f"{diagnosis.ontology_id}.json"
    path.write_text(json.dumps(diagnosis.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return path


def _diagnosis_from_judge_payload(
    payload: dict[str, object],
    fallback: FailureDiagnosis | None,
    *,
    judge_name: str,
    extra_calibration: dict[str, object] | None = None,
) -> FailureDiagnosis | None:
    if payload.get("abstain") is True:
        return None
    diagnosis_payload = payload.get("diagnosis") if isinstance(payload.get("diagnosis"), dict) else payload
    if not isinstance(diagnosis_payload, dict):
        raise ValueError("issue judge response must be a JSON object")
    merged = {
        **(fallback.to_dict() if fallback else {}),
        **diagnosis_payload,
    }
    if fallback and not merged.get("trace_scores"):
        merged["trace_scores"] = [score.to_dict() for score in fallback.trace_scores]
    diagnosis = diagnosis_from_dict(merged)
    calibration = {
        **diagnosis.calibration,
        "judge": judge_name,
        **(extra_calibration or {}),
    }
    return FailureDiagnosis(**{**diagnosis.__dict__, "calibration": calibration})


def _extract_chat_json(response_payload: dict[str, object]) -> dict[str, object]:
    choices = response_payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    parsed = json.loads(content)
                    if isinstance(parsed, dict):
                        return parsed
    if isinstance(response_payload.get("diagnosis"), dict) or response_payload.get("abstain") is True:
        return response_payload
    raise ValueError("issue judge response did not contain JSON content")


def _compact_trace(trace: Trace, max_spans: int = 8) -> dict[str, object]:
    return {
        "trace_id": trace.trace_id,
        "started_at": trace.started_at,
        "inputs": trace.inputs,
        "outputs": trace.outputs,
        "feedback": trace.feedback,
        "metadata": trace.metadata,
        "spans": [
            {
                "span_id": span.span_id,
                "type": span.type,
                "name": span.name,
                "side_effect_class": span.side_effect_class,
                "error": span.error,
                "input": span.input,
                "output": span.output,
            }
            for span in trace.spans[:max_spans]
        ],
    }


def _compact_artifact(artifact: HarnessArtifact) -> dict[str, object]:
    return {
        "artifact_id": artifact.artifact_id,
        "artifact_type": artifact.artifact_type,
        "path": artifact.path,
        "summary": artifact.summary,
        "confidence": artifact.confidence,
        "metadata": {
            "tool_name": artifact.metadata.get("tool_name"),
            "side_effect_class": artifact.metadata.get("side_effect_class"),
            "tools": artifact.metadata.get("tools"),
            "signals": artifact.metadata.get("signals"),
            "embedding_text": artifact.metadata.get("embedding_text"),
        },
    }
