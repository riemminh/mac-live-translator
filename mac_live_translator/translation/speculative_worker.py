"""Worker routine for streaming speculative preview translation."""

from __future__ import annotations

import threading
import time
from typing import Callable

from mac_live_translator.config import Config
from mac_live_translator.translation.models import SpeculativeJob
from mac_live_translator.translation.ollama import TranslationCancelled, translate_stream
from mac_live_translator.translation.scheduler import TranslationScheduler


def execute_speculative_job(
    cfg: Config,
    scheduler: TranslationScheduler,
    job: SpeculativeJob,
    emit: Callable[[str, dict], None],
    stop: threading.Event,
) -> None:
    """Stream an early speculative Vietnamese translation for uncommitted speech."""
    if stop.is_set() or job.cancel_event.is_set():
        return

    last_update = 0.0

    def token(text: str) -> None:
        nonlocal last_update
        now = time.monotonic()
        if now - last_update >= 0.06:
            emit("vietnamese_partial", {
                "id": job.segment_id,
                "text": text.strip(),
                "status": "draft",
                "is_draft": True,
                "is_speculative": True,
                "revision": job.revision,
                "received_at": now,
            })
            last_update = now

    try:
        result = translate_stream(
            " ".join(job.english),
            cfg.translation_model,
            token,
            job.cancel_event,
            context=job.context,
        )
        if result and not job.cancel_event.is_set():
            emit("vietnamese_partial", {
                "id": job.segment_id,
                "text": result.strip(),
                "status": "draft",
                "is_draft": True,
                "is_speculative": True,
                "revision": job.revision,
                "received_at": time.monotonic(),
            })
    except TranslationCancelled:
        pass
    except Exception as exc:
        emit("translation_delayed", {"id": job.segment_id, "reason": f"speculative failed: {exc}"})

