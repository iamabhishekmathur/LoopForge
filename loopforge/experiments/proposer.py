"""Agentic harness-candidate proposer with controlled evidence access."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import difflib
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Protocol
from urllib.request import Request, urlopen

from loopforge.experiments.corpus import assert_no_holdout_leak
from loopforge.experiments.models import (
    CandidateHypothesis,
    ExperimentCandidate,
    ExperimentCase,
    SearchSession,
)
from loopforge.judging.model_judge import _loads_model_json
from loopforge.privacy.redaction import sanitize_for_external_llm


PROPOSER_SYSTEM_PROMPT = """You are LoopForge's harness experiment proposer.

Your goal is to improve the agent harness, not the frozen base model. Investigate source code,
raw search/control traces, and prior experiment results before proposing changes. Use one tool
action at a time. Prefer causal, isolated mutations; state confounds and a disproof condition.
Never ask for or infer hidden holdout data. Do not modify files directly. Finish with a `propose`
action containing complete replacement content for each changed file. Return JSON only.
Prior-session candidates are transferable experience, not valid parents of the active baseline.
"""

OPTIMIZER_SKILL_VERSION = "1.0.0"

PROPOSAL_CONTRACT = {
    "action": "propose",
    "proposals": [
        {
            "parent_candidate_ids": ["candidate ids"],
            "hypothesis": {
                "statement": "causal claim",
                "expected_effect": "observable effect",
                "affected_case_classes": ["classes"],
                "unaffected_case_classes": ["controls"],
                "possible_confounds": ["confounds"],
                "disproof_condition": "result that rejects the hypothesis",
            },
            "file_updates": [
                {
                    "path": "repository-relative path",
                    "expected_sha256": "current file sha256 or empty for a new file",
                    "content": "complete new file content",
                }
            ],
            "risk_assessment": "concise risk",
            "rollback_plan": "how to undo the mutation",
        }
    ],
}


class CandidateProposer(Protocol):
    proposer_id: str

    def propose(
        self,
        workspace: "SearchWorkspace",
        session: SearchSession,
        *,
        round_number: int,
        count: int,
    ) -> list[dict[str, Any]]:
        """Return raw candidate proposals after investigating the workspace."""


@dataclass
class SearchWorkspace:
    root: Path
    issue: dict[str, Any]
    cases: list[ExperimentCase]
    candidates: list[dict[str, Any]]
    evaluations: list[dict[str, Any]]

    def summary(self) -> dict[str, Any]:
        visible = [case for case in self.cases if case.split != "holdout"]
        return {
            "issue": self.issue,
            "available_cases": [
                {
                    "case_id": case.case_id,
                    "split": case.split,
                    "metadata": case.metadata,
                }
                for case in visible
            ],
            "source_files": self._source_inventory(),
            "candidate_summaries": [self._candidate_summary(candidate) for candidate in self.candidates],
            "evaluation_summaries": [self._evaluation_summary(item) for item in self.evaluations],
        }

    def run_action(self, action: dict[str, Any]) -> dict[str, Any]:
        name = str(action.get("action") or "")
        if name == "inspect_trace":
            identifier = str(action.get("trace_id") or action.get("case_id") or "")
            for case in self.cases:
                if identifier in {case.trace_id, case.case_id}:
                    if case.split == "holdout":
                        raise PermissionError("hidden holdout evidence is evaluator-only")
                    return {"action": name, "case": case.to_dict()}
            raise ValueError(f"unknown visible trace or case: {identifier}")
        if name == "inspect_file":
            relative = str(action.get("path") or "")
            path = self._safe_source_path(relative)
            return {
                "action": name,
                "path": relative,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "content": path.read_text(encoding="utf-8"),
            }
        if name == "inspect_candidate":
            candidate_id = str(action.get("candidate_id") or "")
            candidate = next(
                (item for item in self.candidates if item.get("candidate_id") == candidate_id),
                None,
            )
            if candidate is None:
                raise ValueError(f"unknown candidate: {candidate_id}")
            evaluations = [
                self._evaluation_summary(item)
                for item in self.evaluations
                if item.get("candidate_id") == candidate_id
            ]
            return {"action": name, "candidate": candidate, "evaluations": evaluations}
        if name == "compare_candidates":
            identifiers = [str(value) for value in action.get("candidate_ids") or []]
            return {
                "action": name,
                "candidates": [
                    item for item in self.candidates if item.get("candidate_id") in identifiers
                ],
                "evaluations": [
                    self._evaluation_summary(item)
                    for item in self.evaluations
                    if item.get("candidate_id") in identifiers
                ],
            }
        if name == "list_history":
            return {
                "action": name,
                "candidates": [self._candidate_summary(item) for item in self.candidates],
                "evaluations": [self._evaluation_summary(item) for item in self.evaluations],
            }
        raise ValueError(f"unsupported proposer action: {name}")

    def _source_inventory(self) -> list[dict[str, Any]]:
        records = []
        for path in self.root.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(self.root)
            if any(part in {".git", ".loopforge", "node_modules", ".venv", "__pycache__"} for part in relative.parts):
                continue
            if path.suffix.lower() not in {".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".yaml", ".yml", ".json"}:
                continue
            records.append({"path": relative.as_posix(), "bytes": path.stat().st_size})
        return sorted(records, key=lambda item: str(item["path"]))[:2000]

    def _safe_source_path(self, relative: str) -> Path:
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root.resolve()) or not path.is_file() or path.is_symlink():
            raise ValueError(f"source path is not readable: {relative}")
        parts = path.relative_to(self.root.resolve()).parts
        if any(part in {".git", ".loopforge", "node_modules", ".venv"} for part in parts):
            raise ValueError(f"source path is protected: {relative}")
        return path

    @staticmethod
    def _candidate_summary(candidate: dict[str, Any]) -> dict[str, Any]:
        return {
            "candidate_id": candidate.get("candidate_id"),
            "session_id": candidate.get("session_id"),
            "round_number": candidate.get("round_number"),
            "parent_candidate_ids": candidate.get("parent_candidate_ids"),
            "hypothesis": candidate.get("hypothesis"),
            "status": candidate.get("status"),
            "changed_paths": [item.get("path") for item in candidate.get("file_updates") or []],
        }

    @staticmethod
    def _evaluation_summary(evaluation: dict[str, Any]) -> dict[str, Any]:
        visible_cases = [
            case
            for case in evaluation.get("cases") or []
            if case.get("split") != "holdout"
        ]
        return {
            "candidate_id": evaluation.get("candidate_id"),
            "status": evaluation.get("status"),
            "search_control_summary": _visible_objective_summary(visible_cases),
            "case_results": [
                {
                    key: case.get(key)
                    for key in ("case_id", "split", "status", "candidate_quality", "candidate_issue_resolution", "regression_free", "rationale")
                }
                for case in visible_cases
            ],
        }


@dataclass(frozen=True)
class OpenAICompatibleCandidateProposer:
    endpoint: str
    model: str
    api_key_env: str = "OPENAI_API_KEY"
    timeout_seconds: float = 180.0
    max_steps: int = 24
    proposer_id: str = "openai-harness-proposer-v1"

    def propose(
        self,
        workspace: SearchWorkspace,
        session: SearchSession,
        *,
        round_number: int,
        count: int,
    ) -> list[dict[str, Any]]:
        request: dict[str, Any] = {
            "task": f"Investigate and propose {count} distinct harness candidates for round {round_number}.",
            "session": {
                "session_id": session.session_id,
                "issue_id": session.issue_id,
                "baseline_state_id": session.baseline_state_id,
            },
            "optimizer_skill_version": OPTIMIZER_SKILL_VERSION,
            "workspace": workspace.summary(),
            "available_actions": {
                "inspect_trace": {"case_id": "visible opaque case id"},
                "inspect_file": {"path": "source path"},
                "inspect_candidate": {"candidate_id": "candidate id"},
                "compare_candidates": {"candidate_ids": ["candidate ids"]},
                "list_history": {},
                "propose": PROPOSAL_CONTRACT,
            },
        }
        assert_no_holdout_leak(request, workspace.cases)
        transcript: list[dict[str, Any]] = []
        for _ in range(self.max_steps):
            response = self._request({**request, "tool_transcript": transcript})
            assert_no_holdout_leak(response, workspace.cases)
            if response.get("action") == "propose":
                proposals = list(response.get("proposals") or [])
                if len(proposals) != count:
                    raise ValueError(f"proposer returned {len(proposals)} candidates; expected {count}")
                return proposals
            observation = workspace.run_action(response)
            transcript.append({"request": response, "observation": observation})
        raise ValueError("candidate proposer exhausted its evidence-inspection budget")

    def _request(self, packet: dict[str, Any]) -> dict[str, Any]:
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise ValueError(f"missing API key environment variable: {self.api_key_env}")
        sanitized = sanitize_for_external_llm(packet)
        body = {
            "model": self.model,
            "temperature": 0.25,
            "max_tokens": 6000,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": PROPOSER_SYSTEM_PROMPT},
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
                if not isinstance(parsed, dict):
                    raise ValueError("candidate proposer returned a non-object")
                return parsed
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
        raise ValueError(f"candidate proposer request failed: {last_error}") from last_error


def materialize_candidates(
    root: Path,
    session: SearchSession,
    proposals: list[dict[str, Any]],
    *,
    round_number: int,
    proposer_id: str,
    created_at: str | None = None,
) -> list[ExperimentCandidate]:
    now = created_at or datetime.now(UTC).isoformat()
    candidates: list[ExperimentCandidate] = []
    statements: set[str] = set()
    for index, proposal in enumerate(proposals, start=1):
        hypothesis = CandidateHypothesis.from_dict(dict(proposal.get("hypothesis") or {}))
        normalized = " ".join(hypothesis.statement.lower().split())
        if normalized in statements:
            raise ValueError("candidate hypotheses must be distinct")
        statements.add(normalized)
        file_updates = list(proposal.get("file_updates") or [])
        if not file_updates:
            raise ValueError("candidate must change at least one harness artifact")
        digest = hashlib.sha256(
            json.dumps(
                {
                    "session": session.session_id,
                    "round": round_number,
                    "index": index,
                    "hypothesis": hypothesis.to_dict(),
                    "updates": file_updates,
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()[:12]
        candidate_id = f"CANDIDATE-{digest}"
        diff = _candidate_diff(root, file_updates)
        target_artifacts = [
            {
                "path": update.get("path"),
                "sha256": update.get("expected_sha256")
                or hashlib.sha256(b"").hexdigest(),
                "artifact_type": "harness_component",
                "confidence": 1.0,
            }
            for update in file_updates
        ]
        patch_bundle = {
            "schema_version": "1",
            "patch_id": f"PATCH-{candidate_id}",
            "issue_id": session.issue_id,
            "target_artifacts": target_artifacts,
            "diff": diff,
            "new_eval_ids": [],
            "risk_assessment": str(proposal.get("risk_assessment") or "Requires experiment evaluation."),
            "rollback_plan": str(proposal.get("rollback_plan") or "Revert the candidate diff."),
            "status": "experimental",
            "metadata": {
                "search_session_id": session.session_id,
                "candidate_id": candidate_id,
                "optimizer_skill_version": OPTIMIZER_SKILL_VERSION,
                "requires_human_approval": True,
            },
        }
        candidates.append(
            ExperimentCandidate(
                candidate_id=candidate_id,
                session_id=session.session_id,
                round_number=round_number,
                parent_candidate_ids=list(proposal.get("parent_candidate_ids") or [])
                or [f"BASELINE-{session.session_id}"],
                hypothesis=hypothesis,
                file_updates=file_updates,
                patch_bundle=patch_bundle,
                status="proposed",
                created_at=now,
                proposer_id=proposer_id,
                metadata={
                    "mutation_count": len(file_updates),
                    "optimizer_skill_version": OPTIMIZER_SKILL_VERSION,
                },
            )
        )
    return candidates


def _candidate_diff(root: Path, updates: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    for update in updates:
        relative = str(update.get("path") or "")
        path = root / relative
        original = path.read_text(encoding="utf-8") if path.is_file() else ""
        content = str(update.get("content") or "")
        chunks.extend(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                content.splitlines(keepends=True),
                fromfile=relative,
                tofile=relative,
            )
        )
    return "".join(chunks)


def _visible_objective_summary(cases: list[dict[str, Any]]) -> dict[str, float]:
    def mean(key: str, *, split: str | None = None) -> float:
        values = [
            float(case[key])
            for case in cases
            if key in case and (split is None or case.get("split") == split)
        ]
        return round(sum(values) / len(values), 4) if values else 0.0

    return {
        "quality": mean("candidate_quality"),
        "issue_resolution": mean("candidate_issue_resolution", split="search"),
        "regression_free": mean("regression_free", split="control"),
        "judge_confidence": mean("confidence"),
    }
