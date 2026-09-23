"""Evidence-preserving reducers with verifiable receipts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from loopforge.evidence.archive import EvidenceRecord, archive_dir, evidence_text, list_evidence


@dataclass(frozen=True)
class EvidenceQuote:
    text: str
    start: int
    end: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceQuote":
        return cls(text=str(data["text"]), start=int(data["start"]), end=int(data["end"]))

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "start": self.start, "end": self.end}


@dataclass(frozen=True)
class ReductionReceipt:
    receipt_id: str
    evidence_id: str
    source_sha256: str
    reducer: str
    created_at: str
    source_bytes: int
    reduced_bytes: int
    compression_ratio: float
    verification_status: str
    summary: str
    quotes: list[EvidenceQuote]
    failures: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReductionReceipt":
        return cls(
            receipt_id=str(data["receipt_id"]),
            evidence_id=str(data["evidence_id"]),
            source_sha256=str(data["source_sha256"]),
            reducer=str(data["reducer"]),
            created_at=str(data["created_at"]),
            source_bytes=int(data["source_bytes"]),
            reduced_bytes=int(data["reduced_bytes"]),
            compression_ratio=float(data["compression_ratio"]),
            verification_status=str(data["verification_status"]),
            summary=str(data["summary"]),
            quotes=[EvidenceQuote.from_dict(item) for item in data.get("quotes") or []],
            failures=[str(item) for item in data.get("failures") or []],
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "receipt_id": self.receipt_id,
            "evidence_id": self.evidence_id,
            "source_sha256": self.source_sha256,
            "reducer": self.reducer,
            "created_at": self.created_at,
            "source_bytes": self.source_bytes,
            "reduced_bytes": self.reduced_bytes,
            "compression_ratio": self.compression_ratio,
            "verification_status": self.verification_status,
            "summary": self.summary,
            "quotes": [quote.to_dict() for quote in self.quotes],
            "failures": self.failures,
            "metadata": self.metadata,
        }


def reduce_all_evidence(root: Path, *, limit: int | None = None) -> list[ReductionReceipt]:
    records = list_evidence(root)
    if limit is not None:
        records = records[:limit]
    receipts = [reduce_evidence(root, record) for record in records]
    _write_receipt_index(root, receipts)
    return receipts


def reduce_evidence(root: Path, record: EvidenceRecord) -> ReductionReceipt:
    source = evidence_text(root, record)
    quotes = _quote_candidates(source)
    summary = _summary_from_quotes(record, quotes)
    receipt_payload = {
        "evidence_id": record.evidence_id,
        "source_sha256": record.content_sha256,
        "summary": summary,
        "quotes": [quote.to_dict() for quote in quotes],
    }
    reduced_bytes = len(json.dumps(receipt_payload, sort_keys=True).encode("utf-8"))
    failures = _verify_receipt(record, source, quotes, reduced_bytes)
    status = "verified" if not failures else "failed"
    receipt_id = _receipt_id(record.evidence_id, record.content_sha256, summary, quotes)
    receipt = ReductionReceipt(
        receipt_id=receipt_id,
        evidence_id=record.evidence_id,
        source_sha256=record.content_sha256,
        reducer="local_quote_receipt_v1",
        created_at=datetime.now(UTC).isoformat(),
        source_bytes=record.byte_count,
        reduced_bytes=reduced_bytes,
        compression_ratio=round(reduced_bytes / max(1, record.byte_count), 4),
        verification_status=status,
        summary=summary,
        quotes=quotes,
        failures=failures,
        metadata={
            "source_type": record.source_type,
            "source_id": record.source_id,
        },
    )
    _write_receipt(root, receipt)
    return receipt


def list_receipts(root: Path) -> list[ReductionReceipt]:
    receipts_dir = archive_dir(root) / "receipts"
    if not receipts_dir.exists():
        return []
    receipts = [
        ReductionReceipt.from_dict(json.loads(path.read_text(encoding="utf-8")))
        for path in receipts_dir.glob("ER-*.json")
    ]
    return sorted(receipts, key=lambda item: item.receipt_id)


def get_receipt(root: Path, receipt_id: str) -> ReductionReceipt | None:
    path = archive_dir(root) / "receipts" / f"{receipt_id}.json"
    if not path.exists():
        return None
    return ReductionReceipt.from_dict(json.loads(path.read_text(encoding="utf-8")))


def receipts_for_trace(root: Path, trace_id: str) -> list[ReductionReceipt]:
    receipts = []
    for receipt in list_receipts(root):
        source_id = str(receipt.metadata.get("source_id") or "")
        if source_id == trace_id or source_id.startswith(f"{trace_id}:"):
            receipts.append(receipt)
    return sorted(receipts, key=lambda item: item.receipt_id)


def _quote_candidates(source: str) -> list[EvidenceQuote]:
    strings = _string_values(json.loads(source))
    quotes: list[EvidenceQuote] = []
    seen: set[str] = set()
    for text in strings:
        clean = re.sub(r"\s+", " ", text).strip()
        if len(clean) < 24 or clean in seen:
            continue
        encoded = json.dumps(text, ensure_ascii=False)[1:-1]
        start = source.find(encoded)
        if start < 0:
            continue
        quote_text = encoded[:500]
        quotes.append(EvidenceQuote(text=quote_text, start=start, end=start + len(quote_text)))
        seen.add(clean)
        if len(quotes) >= 5:
            break
    if not quotes:
        fallback = source[:500]
        quotes.append(EvidenceQuote(text=fallback, start=0, end=len(fallback)))
    return quotes


def _string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            values.extend(_string_values(item))
        return values
    if isinstance(value, dict):
        values = []
        preferred = (
            "user_message",
            "user_query",
            "question",
            "assistant_message",
            "final_response",
            "answer",
            "response",
            "summary",
            "reasoning",
            "content",
            "textToSQLSummary",
            "db_query",
        )
        for key in preferred:
            if key in value:
                values.extend(_string_values(value[key]))
        for key, item in value.items():
            if key not in preferred:
                values.extend(_string_values(item))
        return values
    return []


def _summary_from_quotes(record: EvidenceRecord, quotes: list[EvidenceQuote]) -> str:
    quote_text = " ".join(quote.text for quote in quotes[:3])
    quote_text = re.sub(r"\s+", " ", quote_text).strip()
    if len(quote_text) > 700:
        quote_text = quote_text[:700] + "..."
    return f"{record.source_type} `{record.source_id}` evidence: {quote_text}"


def _verify_receipt(
    record: EvidenceRecord,
    source: str,
    quotes: list[EvidenceQuote],
    reduced_bytes: int,
) -> list[str]:
    failures = []
    if hashlib.sha256(source.encode("utf-8")).hexdigest() != record.content_sha256:
        failures.append("source_hash_mismatch")
    for quote in quotes:
        if quote.text not in source:
            failures.append(f"quote_not_found:{quote.start}:{quote.end}")
    if reduced_bytes >= record.byte_count:
        failures.append("no_size_reduction")
    if not quotes:
        failures.append("missing_quotes")
    return failures


def _write_receipt(root: Path, receipt: ReductionReceipt) -> None:
    receipts_dir = archive_dir(root) / "receipts"
    receipts_dir.mkdir(parents=True, exist_ok=True)
    path = receipts_dir / f"{receipt.receipt_id}.json"
    path.write_text(json.dumps(receipt.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_receipt_index(root: Path, receipts: list[ReductionReceipt]) -> None:
    path = archive_dir(root) / "receipts-index.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([receipt.to_dict() for receipt in receipts], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _receipt_id(
    evidence_id: str,
    source_sha256: str,
    summary: str,
    quotes: list[EvidenceQuote],
) -> str:
    payload = json.dumps(
        {
            "evidence_id": evidence_id,
            "source_sha256": source_sha256,
            "summary": summary,
            "quotes": [quote.to_dict() for quote in quotes],
        },
        sort_keys=True,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"ER-{digest[:12]}"
