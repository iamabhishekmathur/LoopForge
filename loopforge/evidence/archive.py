"""Durable local evidence archive."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from loopforge.paths import LOCAL_DIR


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    source_type: str
    source_id: str
    content_sha256: str
    byte_count: int
    content_path: str
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceRecord":
        return cls(
            evidence_id=str(data["evidence_id"]),
            source_type=str(data["source_type"]),
            source_id=str(data["source_id"]),
            content_sha256=str(data["content_sha256"]),
            byte_count=int(data["byte_count"]),
            content_path=str(data["content_path"]),
            created_at=str(data["created_at"]),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "evidence_id": self.evidence_id,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "content_sha256": self.content_sha256,
            "byte_count": self.byte_count,
            "content_path": self.content_path,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


def archive_dir(root: Path) -> Path:
    return root / LOCAL_DIR / "evidence"


def archive_object(
    root: Path,
    *,
    source_type: str,
    source_id: str,
    payload: Any,
    metadata: dict[str, Any] | None = None,
) -> EvidenceRecord:
    evidence_root = archive_dir(root)
    objects_dir = evidence_root / "objects"
    objects_dir.mkdir(parents=True, exist_ok=True)
    raw = _canonical_json(payload)
    digest = hashlib.sha256(raw).hexdigest()
    evidence_id = _evidence_id(source_type, source_id, digest)
    content_path = objects_dir / f"{digest}.json"
    if not content_path.exists():
        content_path.write_bytes(raw)

    record = EvidenceRecord(
        evidence_id=evidence_id,
        source_type=source_type,
        source_id=source_id,
        content_sha256=digest,
        byte_count=len(raw),
        content_path=str(content_path.relative_to(root)),
        created_at=datetime.now(UTC).isoformat(),
        metadata=metadata or {},
    )
    _upsert_index(root, record)
    return record


def archive_trace(root: Path, trace: dict[str, Any]) -> list[EvidenceRecord]:
    records = [
        archive_object(
            root,
            source_type="trace",
            source_id=str(trace["trace_id"]),
            payload=trace,
            metadata={
                "trace_id": trace.get("trace_id"),
                "started_at": trace.get("started_at"),
                "span_count": len(trace.get("spans") or []),
            },
        )
    ]
    for span in trace.get("spans") or []:
        if not isinstance(span, dict):
            continue
        span_id = str(span.get("span_id") or "")
        if not span_id:
            continue
        records.append(
            archive_object(
                root,
                source_type="span",
                source_id=f"{trace['trace_id']}:{span_id}",
                payload=span,
                metadata={
                    "trace_id": trace.get("trace_id"),
                    "span_id": span_id,
                    "span_name": span.get("name"),
                    "span_type": span.get("type"),
                },
            )
        )
    return records


def list_evidence(root: Path) -> list[EvidenceRecord]:
    index = _read_index(root)
    records = [EvidenceRecord.from_dict(item) for item in index.values()]
    return sorted(records, key=lambda item: (item.source_type, item.source_id, item.evidence_id))


def get_evidence(root: Path, evidence_id: str) -> tuple[EvidenceRecord, Any] | None:
    index = _read_index(root)
    payload = index.get(evidence_id)
    if payload is None:
        return None
    record = EvidenceRecord.from_dict(payload)
    path = root / record.content_path
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != record.content_sha256:
        raise ValueError(f"evidence content hash mismatch: {evidence_id}")
    return record, json.loads(content.decode("utf-8"))


def evidence_text(root: Path, record: EvidenceRecord) -> str:
    path = root / record.content_path
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != record.content_sha256:
        raise ValueError(f"evidence content hash mismatch: {record.evidence_id}")
    return content.decode("utf-8")


def _read_index(root: Path) -> dict[str, dict[str, Any]]:
    path = archive_dir(root) / "index.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_index(root: Path, index: dict[str, dict[str, Any]]) -> None:
    path = archive_dir(root) / "index.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _upsert_index(root: Path, record: EvidenceRecord) -> None:
    index = _read_index(root)
    index[record.evidence_id] = record.to_dict()
    _write_index(root, index)


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _evidence_id(source_type: str, source_id: str, content_sha256: str) -> str:
    digest = hashlib.sha256(f"{source_type}:{source_id}:{content_sha256}".encode("utf-8")).hexdigest()
    return f"EV-{digest[:12]}"

