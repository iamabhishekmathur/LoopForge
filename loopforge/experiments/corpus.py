"""Build isolated search, control, and hidden-holdout corpora."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
import time
from typing import Protocol
from urllib.request import Request, urlopen

from loopforge.experiments.models import ExperimentCase
from loopforge.models.issue import Issue
from loopforge.models.trace import Trace
from loopforge.judging.model_judge import _loads_model_json
from loopforge.privacy.redaction import sanitize_for_external_llm


VALID_SPLITS = {"search", "control", "holdout"}


@dataclass(frozen=True)
class CaseAssignment:
    trace_id: str
    split: str
    rationale: str


class CaseCurator(Protocol):
    curator_id: str

    def assign(self, issue: Issue, traces: list[Trace]) -> list[CaseAssignment]:
        """Assign each eligible trace to one experiment split."""


@dataclass(frozen=True)
class EvidenceSplitCurator:
    """Reproducible fallback that uses existing model-qualified issue evidence.

    This curator does not make a new semantic judgment. It places traces already
    qualified as issue evidence into search and reserves unrelated traces for
    controls and hidden holdout. Live deployments should use a model curator.
    """

    curator_id: str = "qualified-evidence-split-v1"

    def assign(self, issue: Issue, traces: list[Trace]) -> list[CaseAssignment]:
        evidence = set(issue.evidence_trace_ids)
        remaining = sorted(trace.trace_id for trace in traces if trace.trace_id not in evidence)
        assignments = [
            CaseAssignment(trace_id=trace.trace_id, split="search", rationale="qualified issue evidence")
            for trace in traces
            if trace.trace_id in evidence
        ]
        for index, trace_id in enumerate(remaining):
            split = "holdout" if index % 3 == 0 else "control"
            assignments.append(
                CaseAssignment(
                    trace_id=trace_id,
                    split=split,
                    rationale="reserved non-issue trace",
                )
            )
        return assignments


@dataclass(frozen=True)
class OpenAICompatibleCaseCurator:
    endpoint: str
    model: str
    api_key_env: str = "OPENAI_API_KEY"
    timeout_seconds: float = 120.0
    curator_id: str = "openai-case-curator-v1"

    def assign(self, issue: Issue, traces: list[Trace]) -> list[CaseAssignment]:
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise ValueError(f"missing API key environment variable: {self.api_key_env}")
        aliases = {f"TRACE-{index:04d}": trace for index, trace in enumerate(traces, start=1)}
        packet = {
            "task": (
                "Assign every trace exactly once. Put representative issue examples in search, "
                "successful or acceptable behavior in control, and semantically diverse unseen "
                "examples in holdout. All three splits must be non-empty. Do not use an ontology."
            ),
            "issue": issue.to_dict(),
            "traces": [
                {"trace_ref": alias, "trace": _trace_without_identifiers(trace)}
                for alias, trace in aliases.items()
            ],
            "output_contract": {
                "assignments": [
                    {"trace_ref": "supplied opaque trace reference", "split": "search|control|holdout", "rationale": "concise reason"}
                ]
            },
        }
        sanitized = sanitize_for_external_llm(packet)
        body = {
            "model": self.model,
            "temperature": 0.1,
            "max_tokens": 4000,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You curate agent-harness experiment data. Preserve behavioral diversity, "
                        "separate acceptable controls from failures, and reserve a hidden holdout. "
                        "Return JSON only."
                    ),
                },
                {"role": "user", "content": json.dumps(sanitized.value, sort_keys=True)},
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
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                parsed = _loads_model_json(payload["choices"][0]["message"]["content"])
                assignments = [
                    CaseAssignment(
                        trace_id=aliases[str(item["trace_ref"])].trace_id,
                        split=str(item["split"]),
                        rationale=str(item.get("rationale") or "model-curated split"),
                    )
                    for item in parsed.get("assignments") or []
                ]
                if len(assignments) != len(traces):
                    raise ValueError("case curator must assign every supplied trace exactly once")
                return assignments
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
        raise ValueError(f"case curator request failed: {last_error}") from last_error


def _trace_without_identifiers(trace: Trace) -> dict[str, object]:
    payload = trace.to_dict()
    payload.pop("trace_id", None)
    payload.pop("source_trace_id", None)
    payload.pop("session_id", None)
    return payload


def build_corpus(
    session_id: str,
    issue: Issue,
    traces: list[Trace],
    curator: CaseCurator,
    *,
    created_at: str,
) -> list[ExperimentCase]:
    trace_by_id = {trace.trace_id: trace for trace in traces}
    assignments = curator.assign(issue, traces)
    _validate_assignments(assignments, trace_by_id)
    return [
        ExperimentCase(
            case_id=_case_id(session_id, assignment.trace_id),
            session_id=session_id,
            trace_id=assignment.trace_id,
            split=assignment.split,
            created_at=created_at,
            payload=trace_by_id[assignment.trace_id].to_dict(),
            metadata={
                "curator_id": curator.curator_id,
                "rationale": assignment.rationale,
            },
        )
        for assignment in assignments
    ]


def proposer_visible_cases(cases: list[ExperimentCase]) -> list[dict[str, object]]:
    """Return only evidence the proposer is authorized to inspect."""

    return [case.to_dict() for case in cases if case.split != "holdout"]


def assert_no_holdout_leak(value: object, cases: list[ExperimentCase]) -> None:
    """Fail closed when serialized proposer context mentions hidden identifiers."""

    serialized = repr(value)
    leaked = [
        case.case_id
        for case in cases
        if case.split == "holdout"
        and (case.case_id in serialized or case.trace_id in serialized)
    ]
    if leaked:
        raise ValueError(f"holdout isolation violation: {', '.join(sorted(leaked))}")


def split_counts(cases: list[ExperimentCase]) -> dict[str, int]:
    return {
        split: sum(case.split == split for case in cases)
        for split in sorted(VALID_SPLITS)
    }


def _validate_assignments(
    assignments: list[CaseAssignment], trace_by_id: dict[str, Trace]
) -> None:
    seen: set[str] = set()
    for assignment in assignments:
        if assignment.split not in VALID_SPLITS:
            raise ValueError(f"invalid experiment split: {assignment.split}")
        if assignment.trace_id not in trace_by_id:
            raise ValueError(f"curator selected an unknown trace: {assignment.trace_id}")
        if assignment.trace_id in seen:
            raise ValueError(f"trace assigned more than once: {assignment.trace_id}")
        seen.add(assignment.trace_id)
    if not any(assignment.split == "search" for assignment in assignments):
        raise ValueError("search corpus requires at least one issue case")
    if not any(assignment.split == "control" for assignment in assignments):
        raise ValueError("search corpus requires at least one acceptable control")
    if not any(assignment.split == "holdout" for assignment in assignments):
        raise ValueError("search corpus requires at least one hidden holdout case")


def _case_id(session_id: str, trace_id: str) -> str:
    digest = hashlib.sha256(f"{session_id}:{trace_id}".encode("utf-8")).hexdigest()[:12]
    return f"CASE-{digest}"
