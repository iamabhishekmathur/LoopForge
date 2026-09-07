"""Trace adapter interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from loopforge.models.trace import Trace


class TraceAdapter(ABC):
    """A source adapter that yields normalized LoopForge traces."""

    id: str

    @abstractmethod
    def read(self, root: Path) -> list[Trace]:
        """Read traces from a source relative to a project root."""
