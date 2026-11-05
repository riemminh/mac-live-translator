"""Execution handlers for streaming fragment and reconciliation jobs."""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable

from mac_live_translator.config import Config
from mac_live_translator.pipeline.metrics import trace
from mac_live_translator.translation.models import Fragment, Segment
from mac_live_translator.translation.ollama import TranslationCancelled, translate, translate_stream
from mac_live_translator.translation.reconcile import check_should_reconcile, maybe_finalize
from mac_live_translator.translation.scheduler import TranslationScheduler


def execute_reconcile_job(
    cfg: Config,
    scheduler: TranslationScheduler,
    seg: Segment,
    rec_text: str,
    emit: Callable[[str, dict], None],
    recent_final_en: deque[str],
    speech_pipe: object = None,
) -> None:
    """Retranslate full finalized English sentence to improve Vietnamese phrasing."""
    trace(emit, seg, "reconciliation_start")
    try:
        rec_result = translate(rec_text, cfg.translation_model)
    except Exception as exc:
        emit("translation_delayed", {"id": seg.id, "reason": f"reconciliation failed: {exc}"})
        maybe_finalize(seg, scheduler, recent_final_en, emit, speech_pipe=speech_pipe)
        return
    with scheduler.cv:
        if seg.finished:
            return
        seg.reconciled = True
        for f in seg.fragments:
            f.status = "done"
    trace(emit, seg, "reconciliation_done")
    maybe_finalize(seg, scheduler, recent_final_en, emit, reconciled_text=rec_result, speech_pipe=speech_pipe)


def execute_fragment_job(
    cfg: Config,
    scheduler: TranslationScheduler,
    seg: Segment,
    frag: Fragment,
    emit: Callable[[str, dict], None],
    stop: threading.Event,
    dropped: dict[str, int],
    recent_final_en: deque[str],
    speech_pipe: object = None,
) -> None:
    """Translate an incremental stable fragment and emit streaming partial updates."""
    now = time.monotonic()
    with scheduler.cv:
        if frag not in seg.fragments or seg.finished:
            dropped["translation"] += 1
            return
        frag.dequeued_at = now
        frag.status = "translating"
    trace(emit, seg, "dequeued", fragment_id=frag.id, wait=now - frag.queued_at)

    cancel = threading.Event()
    last_update = 0.0

    def request_start() -> None:
        frag.request_start_at = time.monotonic()
        trace(emit, seg, "ollama_request_start", fragment_id=frag.id, wait=frag.request_start_at - frag.dequeued_at)

    def token(text: str) -> None:
        nonlocal last_update
        t_now = time.monotonic()
        with scheduler.cv:
            if frag not in seg.fragments:
                return
            first = seg.first_vi_token_received_at is None
            if first:
                seg.first_vi_token_received_at = t_now
            if not frag.first_token_at:
                frag.first_token_at = t_now
            prev_vi = " ".join(item.vietnamese for item in seg.fragments if item is not frag and item.status == "done")
            revision = seg.revision
        if first:
            trace(emit, seg, "first_token_received", fragment_id=frag.id)
        if first or t_now - last_update >= 0.05:
            preview = " ".join(part for part in (prev_vi, text) if part).strip()
            emit("vietnamese_partial", {
                "id": seg.id,
                "fragment_id": frag.id,
                "text": preview,
                "status": "stable",
                "is_draft": False,
                "is_speculative": False,
                "revision": revision,
                "latency": t_now - seg.started,
                "received_at": t_now,
                "is_filler": seg.is_filler,
            })
            last_update = t_now

    req_start = time.monotonic()
    try:
        result = translate_stream(
            " ".join(frag.english),
            cfg.translation_model,
            token,
            cancel if not stop.is_set() else stop,
            on_request_start=request_start,
            on_stats=lambda stats: emit("ollama_stats", {
                "id": seg.id,
                "fragment_id": frag.id,
                "load_ms": stats.get("load_duration", 0) / 1_000_000,
                "prompt_ms": stats.get("prompt_eval_duration", 0) / 1_000_000,
                "eval_ms": stats.get("eval_duration", 0) / 1_000_000,
            }),
            context=frag.context,
        )
    except TranslationCancelled:
        dropped["translation"] += 1
        return
    done_time = time.monotonic()
    frag.done_at = done_time

    with scheduler.cv:
        if frag not in seg.fragments or stop.is_set():
            dropped["translation"] += 1
            return
        frag.vietnamese = result
        frag.status = "done"
        preview = " ".join(item.vietnamese for item in seg.fragments if item.vietnamese)
        revision = seg.revision

    trace(emit, seg, "translation_done", fragment_id=frag.id, request_duration=done_time - (frag.request_start_at or req_start))
    emit("vietnamese_partial", {
        "id": seg.id,
        "fragment_id": frag.id,
        "text": preview.strip(),
        "status": "stable",
        "is_draft": False,
        "is_speculative": False,
        "revision": revision,
        "latency": (seg.first_vi_token_received_at or done_time) - seg.started,
        "received_at": done_time,
        "is_filler": seg.is_filler,
    })

    with scheduler.cv:
        all_done = (
            seg.final_english is not None
            and seg.fragments
            and all(f.status == "done" for f in seg.fragments)
            and not seg.finished
        )
        should_reconcile = all_done and check_should_reconcile(seg)

    if should_reconcile:
        with scheduler.cv:
            if not seg.reconciled and not seg.finished and not any(s is seg for s, _, _ in scheduler.low_jobs):
                scheduler.low_jobs.append((seg, seg.final_english, time.monotonic()))
                trace(emit, seg, "reconciliation_queued", queue_size=len(scheduler.low_jobs))
                scheduler.cv.notify()
    else:
        maybe_finalize(seg, scheduler, recent_final_en, emit, speech_pipe=speech_pipe)
