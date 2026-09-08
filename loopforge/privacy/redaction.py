"""Local redaction preview for traces and repo text."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Iterable

from loopforge.adapters.registry import configured_trace_sources
from loopforge.paths import LOCAL_DIR


TEXT_SUFFIXES = {".md", ".txt", ".yaml", ".yml", ".json", ".jsonl", ".py", ".ts", ".tsx", ".js"}
SKIP_PARTS = {".git", ".loopforge", "__pycache__", ".pytest_cache", "node_modules", ".venv", "venv"}

PATTERNS = {
    "email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    "phone": re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b"),
    "api_key": re.compile(r"\b(?:sk|pk|api|key|token)_[A-Za-z0-9_\-]{12,}\b"),
    "bearer_token": re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{16,}\b", re.IGNORECASE),
}


@dataclass(frozen=True)
class RedactionFinding:
    kind: str
    path: str
    line: int
    masked: str

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "path": self.path,
            "line": self.line,
            "masked": self.masked,
        }


@dataclass(frozen=True)
class RedactionPreview:
    status: str
    scanned_files: int
    finding_count: int
    findings: list[RedactionFinding] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "1",
            "status": self.status,
            "scanned_files": self.scanned_files,
            "finding_count": self.finding_count,
            "findings": [finding.to_dict() for finding in self.findings],
        }


def preview_redaction(root: Path, *, path_glob: str | None = None) -> RedactionPreview:
    files = list(_candidate_files(root, path_glob))
    findings: list[RedactionFinding] = []
    for path in files:
        relative_path = path.relative_to(root).as_posix()
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        findings.extend(_find_sensitive_values(relative_path, content))
    return RedactionPreview(
        status="needs_review" if findings else "pass",
        scanned_files=len(files),
        finding_count=len(findings),
        findings=findings[:50],
    )


def write_redaction_preview(root: Path, preview: RedactionPreview) -> Path:
    report_dir = root / LOCAL_DIR / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / "REDACTION-PREVIEW.json"
    path.write_text(json.dumps(preview.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return path


def redaction_preview_markdown(preview: RedactionPreview) -> str:
    lines = [
        "# Redaction Preview",
        "",
        f"Status: `{preview.status}`",
        f"Scanned files: `{preview.scanned_files}`",
        f"Findings: `{preview.finding_count}`",
        "",
        "## Findings",
        "",
    ]
    if not preview.findings:
        lines.append("- No sensitive-looking values found.")
    else:
        for finding in preview.findings:
            lines.append(
                f"- `{finding.kind}` in `{finding.path}:{finding.line}` -> `{finding.masked}`"
            )
    return "\n".join(lines)


def _candidate_files(root: Path, path_glob: str | None) -> Iterable[Path]:
    if path_glob:
        candidates = root.glob(path_glob)
    else:
        trace_paths = [
            source.settings["path"]
            for source in configured_trace_sources(root)
            if source.source_type == "jsonl" and source.settings.get("path")
        ]
        candidates = []
        for trace_path in trace_paths:
            candidates.extend(root.glob(trace_path))
        candidates.extend(root.rglob("*"))
    for path in sorted(set(candidates)):
        if not path.is_file():
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if any(part in SKIP_PARTS for part in path.relative_to(root).parts):
            continue
        yield path


def _find_sensitive_values(path: str, content: str) -> list[RedactionFinding]:
    findings: list[RedactionFinding] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        for kind, pattern in PATTERNS.items():
            for match in pattern.finditer(line):
                findings.append(
                    RedactionFinding(
                        kind=kind,
                        path=path,
                        line=line_number,
                        masked=_mask(match.group(0)),
                    )
                )
    return findings


def _mask(value: str) -> str:
    if len(value) <= 8:
        return "***"
    return value[:3] + "***" + value[-3:]
