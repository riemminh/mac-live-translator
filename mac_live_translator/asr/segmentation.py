"""Continuous streaming audio segmentation, RMS voice detection, and overlapping ASR worker."""

from __future__ import annotations

import math
import queue
import threading
import time
from collections import deque
from typing import TYPE_CHECKING, Callable

import numpy as np
import scipy.signal

from mac_live_translator.asr.stability import common, key, tokens
from mac_live_translator.asr.whisper import ASR_RATE, transcribe
from mac_live_translator.config import Config
from mac_live_translator.pipeline.metrics import trace
from mac_live_translator.translation.models import Fragment, Segment
from mac_live_translator.translation.policy import UNSAFE_ENDINGS, is_filler
from mac_live_translator.translation.reconcile import maybe_finalize
from mac_live_translator.translation.speculative import select_speculative_candidate

if TYPE_CHECKING:
    from mac_live_translator.translation.scheduler import TranslationScheduler


def run_asr_worker(
    cfg: Config,
    blocks: queue.Queue[tuple[int, float, np.ndarray]],
    scheduler: TranslationScheduler,
    emit: Callable[[str, dict], None],
    stop: threading.Event,
    dropped: dict[str, int],
    recent_final_en: deque[str],
) -> None:
    """Read captured audio blocks, segment by speech/pause boundaries, and decode via MLX Whisper."""
    audio: deque[np.ndarray] = deque()
    samples = active = decoded_samples = last_voiced_sample = decoded_voiced_sample = number = last_seq = 0
    seg: Segment | None = None
    last_voice = last_decode = last_spec_at = 0.0
    last_spec: list[str] = []
    rate = cfg.sample_rate

    def decode(final: bool) -> None:
        nonlocal last_decode, decoded_samples, decoded_voiced_sample, last_spec, last_spec_at
        assert seg is not None
        if samples < int(0.45 * rate):
            return
        if final and seg.previous and last_voiced_sample <= decoded_voiced_sample:
            text = seg.previous
        else:
            signal = np.concatenate(tuple(audio))[-int(7 * rate):]
            pcm = scipy.signal.resample_poly(signal, ASR_RATE, rate).astype(np.float32)
            text = transcribe(pcm, cfg.whisper_model).strip()
        now = time.monotonic()
        last_decode = now
        decoded_samples = samples
        decoded_voiced_sample = last_voiced_sample
        if not text or text.casefold() in {"[music]", "(music)"}:
            return
        if seg.first_en_at is None:
            seg.first_en_at = now
            trace(emit, seg, "first_en_ready")
        current = tokens(text)
        seg.is_filler = is_filler(current)

        if final:
            trace(emit, seg, "final_en")
            emit("english_final", {"id": seg.id, "text": text, "latency": now - seg.started, "is_filler": seg.is_filler})
            scheduler.invalidate_from(seg, current, emit)
            with scheduler.cv:
                committed_words = scheduler.committed_words(seg)
                remainder = current[len(committed_words):]
                context = scheduler.build_context(recent_final_en, committed_words)
                seg.final_english = text
                frag = None
                if remainder and len(seg.fragments) == 1 and seg.fragments[0].status == "queued":
                    seg.fragments[0].english = current
                    seg.revision += 1
                    revision = seg.revision
                    scheduler.purge_obsolete_jobs()
                    queue_len = len(scheduler.high_jobs)
                    frag = seg.fragments[0]
                elif remainder:
                    scheduler.purge_obsolete_jobs()
                    if len(scheduler.high_jobs) + len(scheduler.low_jobs) >= 16:
                        dropped["translation"] += 1
                        emit("translation_skipped", {"id": seg.id, "reason": "queue full; stopping to avoid lost words"})
                        raise RuntimeError("Translation queue full; session stopped to avoid losing words")
                    frag = Fragment(seg.revision + 1, remainder, context, time.monotonic())
                    seg.fragments.append(frag)
                    seg.revision += 1
                    revision = seg.revision
                    scheduler.high_jobs.append((seg, frag))
                    scheduler.cv.notify()
                    queue_len = len(scheduler.high_jobs)
            if frag and frag.status == "queued" and any(f is frag for _, f in scheduler.high_jobs):
                trace(emit, seg, "queued", fragment_id=frag.id, revision=revision, queue_size=queue_len)
                emit("coverage", {"id": seg.id, "fragment_id": frag.id, "words": len(remainder), "queue_size": queue_len})
            elif not remainder:
                maybe_finalize(seg, scheduler, recent_final_en, emit)
            return

        previous = tokens(seg.previous)
        stable_count = common(previous, current)
        stable_words = current[:stable_count]
        stable_text = " ".join(stable_words)
        if stable_text and stable_text != seg.stable:
            seg.stable_since = seg.previous_at
            seg.stable_en_at = now
            trace(emit, seg, "stable")
        seg.stable = stable_text
        seg.previous = text
        seg.previous_at = now
        emit("english_partial", {"id": seg.id, "text": text, "stable": stable_text, "latency": now - seg.started, "is_filler": seg.is_filler})
        scheduler.invalidate_from(seg, current, emit)
        with scheduler.cv:
            prefix = scheduler.committed_words(seg)
        pending = stable_words[len(prefix):]

        candidate = None
        if len(pending) >= 4:
            cut = min(len(pending), 8)
            boundaries = [i + 1 for i, w in enumerate(pending[:cut]) if i >= 3 and w.endswith((",", ";", ":", ".", "?", "!"))]
            if boundaries:
                cut = boundaries[-1]
            elif cut == len(pending) and not pending[-1].endswith((".", "?", "!")):
                cut -= 1
            while cut > 0 and key(pending[cut - 1]) in UNSAFE_ENDINGS:
                cut -= 1
            if cut >= 4 and len({key(w) for w in pending[:cut]}) >= 3:
                candidate = pending[:cut]

        if candidate:
            trace(emit, seg, "eligible", stable_wait=now - seg.stable_since)
            scheduler.enqueue(seg, candidate, scheduler.build_context(recent_final_en, prefix), dropped, emit)
        elif cfg.fast_preview:
            spec = select_speculative_candidate(seg, current, prefix, last_spec, last_spec_at, now)
            if spec:
                last_spec = spec
                last_spec_at = now
                scheduler.set_speculative(seg, spec, scheduler.build_context(recent_final_en, prefix))

    while not stop.is_set():
        try:
            current_seq, stamp, block = blocks.get(timeout=0.2)
        except queue.Empty:
            continue
        if last_seq and current_seq != last_seq + 1:
            if seg and seg.previous:
                emit("translation_skipped", {"id": seg.id, "reason": "audio overflow"})
                with scheduler.cv:
                    seg.fragments.clear()
                    seg.revision += 1
                    scheduler.purge_obsolete_jobs()
                emit("vietnamese_cancelled", {"id": seg.id})
            audio.clear()
            samples = active = decoded_samples = last_voiced_sample = decoded_voiced_sample = 0
            seg = None
            scheduler.active_speaking = False
        last_seq = current_seq
        mono = block.mean(axis=1).astype(np.float32)
        rms = float(np.sqrt(np.mean(np.square(mono, dtype=np.float64))))
        voiced = math.isfinite(rms) and rms >= cfg.min_rms
        if voiced and not active:
            active = 1
            number += 1
            seg = Segment(number, stamp)
            last_decode = stamp
            scheduler.active_speaking = True
            last_spec = []
            last_spec_at = 0.0
        if not active:
            continue
        assert seg is not None
        audio.append(mono)
        samples += len(mono)
        if voiced:
            last_voice = stamp + len(mono) / rate
            last_voiced_sample = samples
        now = time.monotonic()
        if (now - last_decode >= 0.75 and samples - decoded_samples >= int(0.45 * rate)
                and samples >= int(0.7 * rate) and voiced):
            decode(False)
        pause = stamp + len(mono) / rate - last_voice
        boundary = 0.55 if seg.previous.rstrip().endswith((".", "?", "!")) else 0.85
        if (samples >= int(1.2 * rate) and pause >= boundary) or samples >= int(7 * rate):
            decode(True)
            audio.clear()
            samples = active = decoded_samples = last_voiced_sample = decoded_voiced_sample = 0
            seg = None
            scheduler.active_speaking = False
            last_spec = []
