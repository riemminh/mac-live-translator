"""Meeting transcript entry and question detection data models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TranscriptEntry:
    """An immutable transcript line with monotonic and wall-clock timestamps."""
    id: int
    text: str
    monotonic_at: float
    wall_at: float
    is_filler: bool = False


@dataclass(frozen=True)
class DetectedQuestion:
    """Reconstructed question spanning one or more transcript segments."""
    text: str
    source_ids: list[int] = field(default_factory=list)
    confidence: float = 1.0
