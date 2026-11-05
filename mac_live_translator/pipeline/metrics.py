"""Tracing and latency measurement helper functions."""

from __future__ import annotations

import time
from typing import Callable
from mac_live_translator.translation.models import Segment


def trace(emit: Callable[[str, dict], None], seg: Segment, stage: str, **extra: object) -> None:
    """Emit a structured timing trace event for a segment milestone."""
    emit("trace", {
        "id": seg.id,
        "stage": stage,
        "at": time.monotonic(),
        "source_start": seg.started,
        **extra,
    })

