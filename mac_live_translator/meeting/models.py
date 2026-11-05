"""Meeting transcript entry data model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptEntry:
    """An immutable transcript line with monotonic and wall-clock timestamps."""
    id: int
    text: str
    monotonic_at: float
    wall_at: float
    is_filler: bool = False

