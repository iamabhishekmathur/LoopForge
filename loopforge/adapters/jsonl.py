"""JSONL trace adapter."""

from __future__ import annotations

import glob
import json
from dataclasses import dataclass
from pathlib import Path

from loopforge.adapters.base import TraceAdapter
from loopforge.models.trace import Trace


@dataclass(frozen=True)
class JsonlTraceAdapter(TraceAdapter):
    path_pattern: str
    id: str = "jsonl"

    def read(self, root: Path) -> list[Trace]:
        pattern = str(root / self.path_pattern)
        traces: list[Trace] = []
        for filename in sorted(glob.glob(pattern)):
            path = Path(filename)
            with path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        payload = json.loads(stripped)
                        traces.append(Trace.from_dict(payload))
                    except Exception as exc:
                        raise ValueError(f"{path}:{line_number}: invalid trace: {exc}") from exc
        return traces
