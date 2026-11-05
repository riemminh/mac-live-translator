"""Translation consumer worker executing streaming fragment, speculative preview, and reconciliation jobs."""

from __future__ import annotations

import threading
from collections import deque
from typing import Callable

from mac_live_translator.config import Config
from mac_live_translator.translation.models import Fragment, Segment, SpeculativeJob
from mac_live_translator.translation.scheduler import TranslationScheduler
from mac_live_translator.translation.speculative_worker import execute_speculative_job
from mac_live_translator.translation.worker_jobs import execute_fragment_job, execute_reconcile_job


def run_translation_worker(
    cfg: Config,
    scheduler: TranslationScheduler,
    emit: Callable[[str, dict], None],
    stop: threading.Event,
    dropped: dict[str, int],
    recent_final_en: deque[str],
    speech_pipe: object = None,
) -> None:
    """Consume translation queue jobs with strict live speech priority and fast speculative preview."""
    while not stop.is_set():
        job_kind: str | None = None
        seg: Segment | None = None
        frag: Fragment | None = None
        rec_text: str | None = None
        spec_job: SpeculativeJob | None = None

        with scheduler.cv:
            while not stop.is_set() and not scheduler.high_jobs and not scheduler.speculative_job and not scheduler.low_jobs:
                scheduler.cv.wait(timeout=0.2)
            if stop.is_set():
                break

            # Priority 1: Required stable/final speech fragments
            if scheduler.high_jobs:
                job_kind = "fragment"
                seg, frag = scheduler.high_jobs.pop(0)
                valid = frag in seg.fragments and not seg.finished

            # Priority 2: Early speculative Vietnamese preview (if enabled)
            elif cfg.fast_preview and scheduler.speculative_job is not None:
                job_kind = "speculative"
                spec_job = scheduler.speculative_job
                scheduler.speculative_job = None
                scheduler.active_speculative_cancel = spec_job.cancel_event
                valid = not spec_job.cancel_event.is_set()

            # Priority 3: Non-urgent reconciliation (only when inference queue is idle)
            elif scheduler.low_jobs and not scheduler.active_speaking:
                job_kind = "reconcile"
                seg, rec_text, _ = scheduler.low_jobs.pop(0)
                valid = not seg.finished and not seg.reconciled
            else:
                valid = False

        if not valid:
            continue

        if job_kind == "fragment" and seg is not None and frag is not None:
            execute_fragment_job(cfg, scheduler, seg, frag, emit, stop, dropped, recent_final_en, speech_pipe)

        elif job_kind == "speculative" and spec_job is not None:
            try:
                execute_speculative_job(cfg, scheduler, spec_job, emit, stop)
            finally:
                with scheduler.cv:
                    if scheduler.active_speculative_cancel is spec_job.cancel_event:
                        scheduler.active_speculative_cancel = None

        elif job_kind == "reconcile" and seg is not None and rec_text is not None:
            execute_reconcile_job(cfg, scheduler, seg, rec_text, emit, recent_final_en, speech_pipe)
