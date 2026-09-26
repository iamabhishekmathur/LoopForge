"""Turn accepted trace findings into non-mutating, code-grounded improvement bundles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Protocol
from urllib.request import Request, urlopen

from loopforge.judging.model_judge import _loads_model_json
from loopforge.paths import LOCAL_DIR
from loopforge.privacy.redaction import sanitize_for_external_llm


SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".yaml", ".yml"}
SKIP_PARTS = {".git", ".loopforge", ".venv", "venv", "node_modules", "__pycache__"}
TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_]{3,}")
TRACEBACK_FILE_PATTERN = re.compile(
    r"File\s+\\?[\"']([^\"']+)\\?[\"']\s*,\s*line\s+\d+"
    r"(?:,\s*in\s+([A-Za-z_][A-Za-z0-9_]*))?"
)
LOW_SIGNAL = {
    "actual", "agent", "assistant", "behavior", "codebase", "error", "expected",
    "finding", "output", "response", "result", "should", "system", "trace",
}


INVESTIGATOR_PROMPT = """You are LoopForge's codebase resolution investigator.

Determine the most likely causal chain behind one cluster of accepted agent-trace findings. Use the supplied code evidence as authoritative. Every file or symbol claim must cite one supplied evidence_id. Do not pretend that a traceback proves which semantic fix is correct: offer competing explanations, inspect caller/callee contracts, and recommend the smallest defensible change. Draft a probabilistic regression evaluator with positive, negative, and abstention behavior. A patch is eligible only when the root cause and ownership are supported by exact code evidence and no material ambiguity remains. Never produce a patch or claim that code was changed. Return JSON only using the supplied contract.
"""

VERIFIER_PROMPT = """You are the independent verifier for a proposed agent-harness improvement plan.

Remove unsupported code ownership, causal, or patch claims. Every retained file and symbol claim must cite an evidence_id present in code_evidence. Preserve multiple remediation options when the evidence cannot distinguish them. Mark patch_eligible false when the root cause is ambiguous, citations are missing, or the proposed regression evaluator lacks positive, negative, and abstention behavior. Do not create new evidence or a code patch. Return JSON only using the supplied contract.
"""

OUTPUT_CONTRACT = {
    "cluster_summary": "concise statement of the repeated failure",
    "root_cause": {
        "hypothesis": "most likely causal chain",
        "confidence": "0..1",
        "evidence_ids": ["code evidence ids"],
    },
    "ownership": [
        {"source_path": "repository-relative path", "symbol": "symbol or null", "evidence_ids": ["id"]}
    ],
    "alternatives": [
        {"hypothesis": "competing explanation", "how_to_disprove": "specific check"}
    ],
    "recommended_change": {
        "summary": "smallest defensible change",
        "source_paths": ["repository-relative paths"],
        "symbols": ["symbols"],
        "evidence_ids": ["code evidence ids"],
    },
    "regression_evaluator": {
        "name": "short evaluator name",
        "positive_behavior": "failure behavior that should be detected",
        "negative_behavior": "acceptable behavior that must pass",
        "abstention_behavior": "conditions where evidence is insufficient",
        "pass_criteria": "probabilistic acceptance criteria",
    },
    "risks": ["remaining risk or assumption"],
    "patch_eligible": "boolean",
}


class ResolutionInvestigator(Protocol):
    def investigate(self, packet: dict[str, Any]) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class ImprovementPlanResult:
    bundle_id: str
    cluster_count: int
    reviewable_count: int
    report_path: Path
    markdown_path: Path


@dataclass(frozen=True)
class OpenAICompatibleResolutionInvestigator:
    endpoint: str
    model: str
    review_model: str | None = None
    api_key_env: str = "OPENAI_API_KEY"
    timeout_seconds: float = 180.0

    def investigate(self, packet: dict[str, Any]) -> dict[str, Any]:
        sanitized = sanitize_for_external_llm(packet)
        draft = self._request(INVESTIGATOR_PROMPT, sanitized.value, self.model)
        verification = {
            "task": "Verify this improvement plan against the supplied evidence.",
            "output_contract": OUTPUT_CONTRACT,
            "code_evidence": sanitized.value.get("code_evidence") or [],
            "finding_cluster": sanitized.value.get("finding_cluster") or {},
            "draft_plan": draft,
        }
        return self._request(VERIFIER_PROMPT, verification, self.review_model or self.model)

    def _request(self, prompt: str, packet: dict[str, Any], model: str) -> dict[str, Any]:
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise ValueError(f"missing API key environment variable: {self.api_key_env}")
        body = {
            "model": model,
            "temperature": 0.2,
            "max_tokens": 5000,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(packet, sort_keys=True)},
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
                content = payload["choices"][0]["message"]["content"]
                parsed = _loads_model_json(content)
                if not isinstance(parsed, dict):
                    raise ValueError("resolution investigator returned a non-object JSON value")
                return parsed
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
        raise ValueError(f"resolution investigator request failed: {last_error}") from last_error


def build_improvement_plan(
    root: Path,
    evaluation_report: Path,
    investigator: ResolutionInvestigator,
) -> ImprovementPlanResult:
    report = json.loads(evaluation_report.read_text(encoding="utf-8"))
    clusters = cluster_accepted_findings(report)
    plans: list[dict[str, Any]] = []
    for cluster in clusters:
        code_evidence = collect_code_evidence(root, cluster)
        packet = {
            "task": "Produce a code-grounded, non-mutating improvement plan.",
            "output_contract": OUTPUT_CONTRACT,
            "finding_cluster": cluster,
            "code_evidence": code_evidence,
        }
        raw_plan = investigator.investigate(packet)
        plans.append(_gate_plan(root, cluster, code_evidence, raw_plan))

    generated_at = datetime.now(timezone.utc).isoformat()
    digest = hashlib.sha256(
        f"{evaluation_report.resolve()}:{generated_at}".encode("utf-8")
    ).hexdigest()[:12]
    bundle_id = f"IMPROVE-{digest}"
    payload = {
        "schema_version": "1",
        "bundle_id": bundle_id,
        "generated_at": generated_at,
        "source_evaluation_report": str(evaluation_report),
        "mode": "dry_run",
        "mutated_customer_code": False,
        "cluster_count": len(clusters),
        "reviewable_count": sum(plan["status"] == "reviewable" for plan in plans),
        "plans": plans,
    }
    directory = root / LOCAL_DIR / "improvements"
    directory.mkdir(parents=True, exist_ok=True)
    report_path = directory / f"{bundle_id}.json"
    markdown_path = directory / f"{bundle_id}.md"
    report_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(improvement_plan_markdown(payload), encoding="utf-8")
    (directory / "latest-improvement-plan.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    return ImprovementPlanResult(
        bundle_id=bundle_id,
        cluster_count=len(clusters),
        reviewable_count=payload["reviewable_count"],
        report_path=report_path,
        markdown_path=markdown_path,
    )


def cluster_accepted_findings(report: dict[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in report.get("records") or []:
        if record.get("status") != "complete":
            continue
        audit = (record.get("audit") or {}).get("calibrated") or {}
        findings = (record.get("calibrated_decision") or {}).get("findings") or []
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            disputed = bool(audit.get("false_positive"))
            signature = _finding_signature(finding)
            grouped.setdefault(signature, []).append(
                {
                    "trace_id": record.get("trace_id"),
                    "finding": finding,
                    "adjudication": {
                        "disputed_as_false_positive": disputed,
                        "rationale": audit.get("rationale"),
                    },
                }
            )
    clusters: list[dict[str, Any]] = []
    for signature, members in grouped.items():
        digest = hashlib.sha256(signature.encode("utf-8")).hexdigest()[:12]
        clusters.append(
            {
                "cluster_id": f"CLUSTER-{digest}",
                "signature": signature,
                "trace_ids": sorted({str(item["trace_id"]) for item in members}),
                "occurrence_count": len(members),
                "disputed": any(
                    item["adjudication"]["disputed_as_false_positive"] for item in members
                ),
                "findings": members,
            }
        )
    return sorted(clusters, key=lambda item: (-item["occurrence_count"], item["cluster_id"]))


def collect_code_evidence(
    root: Path,
    cluster: dict[str, Any],
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    text = json.dumps(cluster, sort_keys=True)
    traceback_paths, traceback_symbols = _traceback_references(text)
    tokens = _query_tokens(text) | traceback_symbols
    candidates: list[tuple[float, str, Path, list[str]]] = []
    for path in _source_files(root):
        relative = path.relative_to(root).as_posix()
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        reasons: list[str] = []
        score = 0.0
        for traceback_path in traceback_paths:
            if traceback_path.endswith(relative) or relative.endswith(traceback_path):
                score += 100.0
                reasons.append(f"traceback_path:{traceback_path}")
        lowered = content.lower()
        matches = sorted(token for token in tokens if token.lower() in lowered)
        score += min(30.0, float(len(matches) * 2))
        reasons.extend(f"identifier:{token}" for token in matches[:8])
        if score > 0:
            candidates.append((score, relative, path, reasons))
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    evidence = []
    for index, (score, relative, path, reasons) in enumerate(candidates[:limit], start=1):
        content = path.read_text(encoding="utf-8")
        evidence.append(
            {
                "evidence_id": f"CODE-{index:03d}",
                "source_path": relative,
                "score": round(score, 2),
                "match_reasons": reasons,
                "snippet": _matching_snippet(content, tokens),
            }
        )
    return evidence


def improvement_plan_markdown(bundle: dict[str, Any]) -> str:
    lines = [
        f"# {bundle['bundle_id']}: Improvement Plan",
        "",
        "Mode: `dry_run`",
        f"Clusters: `{bundle['cluster_count']}`",
        f"Reviewable: `{bundle['reviewable_count']}`",
        "",
        "No customer code was modified.",
    ]
    for plan in bundle.get("plans") or []:
        investigation = plan.get("investigation") or {}
        root_cause = investigation.get("root_cause") or {}
        recommendation = investigation.get("recommended_change") or {}
        lines.extend(
            [
                "",
                f"## {plan['cluster_id']}",
                "",
                f"Status: `{plan['status']}`",
                f"Occurrences: `{plan['occurrence_count']}`",
                f"Root cause: {root_cause.get('hypothesis', 'Unresolved')}",
                f"Recommendation: {recommendation.get('summary', 'Further investigation required.')}",
                "",
                "### Acceptance Gates",
                "",
            ]
        )
        lines.extend(f"- `{gate['name']}`: {gate['status']} - {gate['detail']}" for gate in plan["gates"])
    return "\n".join(lines) + "\n"


def _gate_plan(
    root: Path,
    cluster: dict[str, Any],
    code_evidence: list[dict[str, Any]],
    investigation: dict[str, Any],
) -> dict[str, Any]:
    evidence_ids = {str(item["evidence_id"]) for item in code_evidence}
    cited_ids = _collect_values(investigation, "evidence_ids")
    cited_paths = set(_collect_values(investigation, "source_paths"))
    cited_paths.update(
        str(item.get("source_path"))
        for item in investigation.get("ownership") or []
        if isinstance(item, dict) and item.get("source_path")
    )
    invalid_paths = sorted(path for path in cited_paths if not _repository_file_exists(root, path))
    invalid_evidence = sorted(cited_ids - evidence_ids)
    regression = investigation.get("regression_evaluator") or {}
    regression_complete = all(
        regression.get(key)
        for key in ("positive_behavior", "negative_behavior", "abstention_behavior", "pass_criteria")
    )
    try:
        confidence = float((investigation.get("root_cause") or {}).get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0.0
    gates = [
        {
            "name": "code_evidence_present",
            "status": "pass" if code_evidence else "fail",
            "detail": f"{len(code_evidence)} repository evidence records found.",
        },
        {
            "name": "citations_resolve",
            "status": "pass" if cited_ids and not invalid_evidence and not invalid_paths else "fail",
            "detail": (
                f"invalid evidence={invalid_evidence}; invalid paths={invalid_paths}"
                if invalid_evidence or invalid_paths
                else f"{len(cited_ids)} evidence citations resolved."
            ),
        },
        {
            "name": "root_cause_confidence",
            "status": "pass" if confidence >= 0.8 else "fail",
            "detail": f"confidence={confidence:.2f}; required=0.80",
        },
        {
            "name": "regression_evaluator_complete",
            "status": "pass" if regression_complete else "fail",
            "detail": "positive, negative, abstention, and pass criteria are required.",
        },
        {
            "name": "adjudication_not_disputed",
            "status": "pass" if not cluster.get("disputed") else "fail",
            "detail": "The source finding must survive independent adjudication.",
        },
    ]
    passed = all(gate["status"] == "pass" for gate in gates)
    model_eligible = investigation.get("patch_eligible") is True
    return {
        "cluster_id": cluster["cluster_id"],
        "signature": cluster["signature"],
        "trace_ids": cluster["trace_ids"],
        "occurrence_count": cluster["occurrence_count"],
        "status": "reviewable" if passed and model_eligible else "needs_human_review",
        "patch_eligible": bool(passed and model_eligible),
        "auto_apply": False,
        "code_evidence": code_evidence,
        "investigation": investigation,
        "gates": gates,
    }


def _finding_signature(finding: dict[str, Any]) -> str:
    evidence_text = json.dumps(finding.get("supporting_trace_evidence") or [], sort_keys=True)
    error_anchor = _error_anchor(evidence_text)
    if error_anchor:
        anchor = error_anchor
    else:
        anchor = " ".join(str(finding.get("title") or "").lower().split())
    return "|".join(
        [
            str(finding.get("finding_scope") or "unknown"),
            str(finding.get("finding_type") or "unknown"),
            anchor,
        ]
    )


def _error_anchor(text: str) -> str | None:
    for line in text.replace("\\n", "\n").splitlines():
        stripped = line.strip(' \\"')
        if "Error" in stripped or "Exception" in stripped:
            return stripped[:500]
    return None


def _traceback_references(text: str) -> tuple[set[str], set[str]]:
    paths: set[str] = set()
    symbols: set[str] = set()
    normalized = text.replace("\\\\n", "\n").replace("\\n", "\n")
    for match in TRACEBACK_FILE_PATTERN.finditer(normalized):
        paths.add(match.group(1).rstrip("\\").lstrip("/"))
        if match.group(2):
            symbols.add(match.group(2))
    for line in normalized.splitlines():
        stripped = line.strip(' \\"')
        if not stripped.startswith("File ") or '"' not in stripped:
            continue
        parts = stripped.split('"')
        if len(parts) >= 2:
            paths.add(parts[1].lstrip("/"))
        if " in " in stripped:
            symbols.add(stripped.rsplit(" in ", 1)[-1].strip())
    return paths, symbols


def _query_tokens(text: str) -> set[str]:
    tokens = {match.group(0) for match in TOKEN_PATTERN.finditer(text)}
    return {
        token
        for token in tokens
        if token.lower() not in LOW_SIGNAL and ("_" in token or len(token) >= 8)
    }


def _source_files(root: Path) -> list[Path]:
    paths = []
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        relative = path.relative_to(root)
        if any(part in SKIP_PARTS or part.startswith(".") for part in relative.parts):
            continue
        try:
            if path.stat().st_size > 400_000:
                continue
        except OSError:
            continue
        paths.append(path)
    return paths


def _repository_file_exists(root: Path, relative_path: str) -> bool:
    try:
        candidate = (root / relative_path).resolve()
        return candidate.is_relative_to(root.resolve()) and candidate.is_file()
    except (OSError, RuntimeError):
        return False


def _matching_snippet(content: str, tokens: set[str], *, max_chars: int = 2400) -> str:
    lines = content.splitlines()
    lowered_tokens = {token.lower() for token in tokens}
    indexes = [
        index
        for index, line in enumerate(lines)
        if any(token in line.lower() for token in lowered_tokens)
    ]
    if not indexes:
        return "\n".join(lines[:20])[:max_chars]
    start = max(0, indexes[0] - 4)
    end = min(len(lines), indexes[0] + 12)
    return "\n".join(f"{index + 1}: {lines[index]}" for index in range(start, end))[:max_chars]


def _collect_values(value: Any, key: str) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for item_key, item in value.items():
            if item_key == key and isinstance(item, list):
                found.update(str(child) for child in item if child)
            else:
                found.update(_collect_values(item, key))
    elif isinstance(value, list):
        for item in value:
            found.update(_collect_values(item, key))
    return found
