"""Selective reconciliation and final translation assembly."""

from __future__ import annotations

import time
from collections import deque
from typing import Callable

from mac_live_translator.asr.stability import tokens
from mac_live_translator.pipeline.metrics import trace
from mac_live_translator.translation.models import Segment
from mac_live_translator.translation.policy import is_risky_boundary
from mac_live_translator.translation.scheduler import TranslationScheduler


def check_should_reconcile(seg: Segment) -> bool:
    """Determine whether multi-fragment segment contains risky boundaries requiring retranslation."""
    if len(seg.fragments) <= 1 or seg.reconciled or seg.is_filler:
        return False
    for i in range(len(seg.fragments) - 1):
        if is_risky_boundary(seg.fragments[i].english, seg.fragments[i + 1].english):
            return True
    return False


def maybe_finalize(
    seg: Segment,
    scheduler: TranslationScheduler,
    recent_final_en: deque[str],
    emit: Callable[[str, dict], None],
    reconciled_text: str | None = None,
) -> None:
    """Finalize a completed segment and emit coverage and final Vietnamese subtitle events."""
    with scheduler.cv:
        if (
            seg.finished
            or seg.final_english is None
            or not seg.fragments
            or any(frag.status != "done" for frag in seg.fragments)
        ):
            return
        seg.finished = True
        result = reconciled_text if reconciled_text is not None else " ".join(
            frag.vietnamese for frag in seg.fragments
        ).strip()
        revision = seg.revision
        first_received = seg.first_vi_token_received_at
        covered = len(scheduler.committed_words(seg))
        total = len(tokens(seg.final_english))
        fragments_count = len(seg.fragments)
        corrections = seg.corrections
        is_fill = seg.is_filler
        if seg.final_english and not is_fill:
            recent_final_en.append(seg.final_english)

    if result:
        trace(emit, seg, "final_vi")
        emit("coverage_final", {
            "id": seg.id,
            "english_words": total,
            "covered_words": covered,
            "fragments": fragments_count,
            "revisions": corrections,
        })
        emit("vietnamese_final", {
            "id": seg.id,
            "text": result,
            "revision": revision,
            "first_token_received_latency": (first_received - seg.started) if first_received else None,
            "first_token_latency": (first_received - seg.started) if first_received else None,
            "latency": time.monotonic() - seg.started,
            "is_filler": is_fill,
        })

