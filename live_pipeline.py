"""Continuous local capture, overlapping ASR, and sequential streaming translation."""
from __future__ import annotations

import math
import queue
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import scipy.signal
import sounddevice as sd

import main as core


def tokens(text: str) -> list[str]:
    return text.split()


def key(word: str) -> str:
    return re.sub(r"(^[^\w]+|[^\w]+$)", "", word).casefold()


def common(a: list[str], b: list[str]) -> int:
    count = 0
    for left, right in zip(a, b):
        if key(left) != key(right):
            break
        count += 1
    return count


UNSAFE_ENDINGS = {
    # Articles, prepositions, conjunctions
    "a", "an", "the", "and", "or", "but", "nor", "at", "by", "for", "from",
    "in", "into", "of", "on", "to", "with", "without", "than", "as", "if",
    "that", "which", "who", "whom", "whose", "while", "because", "so",
    # Negation and contractions
    "not", "no", "never", "don't", "didn't", "doesn't", "won't", "can't",
    "couldn't", "shouldn't", "wouldn't", "isn't", "aren't", "wasn't", "weren't",
    # Common phrasal verb heads
    "roll", "cut", "sign", "shut", "scale", "spin", "set", "log", "fall",
    "carry", "bring", "point", "pick", "check", "break", "turn", "give", "take",
}

PHRASAL_PARTICLES = {
    "back", "over", "off", "down", "up", "in", "out", "on", "away", "through", "about"
}

NEGATIONS = {
    "not", "no", "never", "cannot", "hardly", "barely", "don't", "didn't",
    "doesn't", "won't", "can't", "couldn't", "shouldn't", "wouldn't",
    "isn't", "aren't", "wasn't", "weren't"
}

SUBORDINATING = {
    "because", "although", "since", "unless", "if", "whether", "while",
    "whereas", "as", "so", "until", "before", "after"
}


def is_risky_boundary(left_words: list[str], right_words: list[str]) -> bool:
    """Detect syntactic boundaries prone to awkward or distorted Vietnamese translations."""
    if not left_words or not right_words:
        return False
    left_last = left_words[-1]
    right_first = right_words[0]
    # Sentence-ending punctuation marks an independent boundary
    if left_last.endswith((".", "?", "!")):
        return False
    if left_last.endswith((";", ":")):
        return False
    left_k = key(left_last)
    right_k = key(right_first)
    if left_k in UNSAFE_ENDINGS:
        return True
    if right_k in PHRASAL_PARTICLES:
        return True
    if left_k in NEGATIONS or right_k in NEGATIONS:
        return True
    if right_k in SUBORDINATING:
        return True
    if left_k.isdigit() or right_k.isdigit() or left_last.endswith("%") or right_first.startswith("$"):
        return True
    # If the left fragment didn't end with a comma, it was sliced mid-clause
    if not left_last.endswith(","):
        return True
    return False


@dataclass(eq=False)
class Fragment:
    id: int
    english: list[str]
    context: str
    queued_at: float
    vietnamese: str = ""
    status: str = "queued"
    dequeued_at: float = 0.0
    request_start_at: float = 0.0
    first_token_at: float = 0.0
    done_at: float = 0.0


@dataclass
class Segment:
    id: int
    started: float
    previous: str = ""
    previous_at: float = 0.0
    stable: str = ""
    stable_since: float = 0.0
    fragments: list[Fragment] = field(default_factory=list)
    final_english: str | None = None
    revision: int = 0
    corrections: int = 0
    first_en_at: float | None = None
    stable_en_at: float | None = None
    first_vi_token_received_at: float | None = None
    first_vi_token_rendered_at: float | None = None
    final_vi_rendered_at: float | None = None
    finished: bool = False
    reconciled: bool = False


def run(cfg: core.Config, emit: Callable[[str, dict], None], stop: threading.Event) -> None:
    core.check_route(cfg)
    core.check_ollama(cfg.translation_model)
    emit("status", {"text": "Loading local models…"})
    core.transcribe(np.zeros(core.ASR_RATE, dtype=np.float32), cfg.whisper_path)
    core.translate("Hello.", cfg.translation_model)
    if stop.is_set():
        return

    blocks: queue.Queue[tuple[int, float, np.ndarray]] = queue.Queue(maxsize=400)
    lock = threading.Lock()
    cv = threading.Condition(lock)
    jobs: list[tuple[Segment, Fragment]] = []
    errors: queue.Queue[Exception] = queue.Queue()
    dropped = {"audio": 0, "translation": 0}
    seq = 0

    def purge_obsolete_jobs() -> None:
        nonlocal jobs
        jobs = [(s, f) for s, f in jobs if f in s.fragments and not s.finished]

    def trace(seg: Segment, stage: str, **extra: object) -> None:
        emit("trace", {"id": seg.id, "stage": stage, "at": time.monotonic(),
                       "source_start": seg.started, **extra})

    def capture(indata: np.ndarray, frames: int, timing: object, status: sd.CallbackFlags) -> None:
        nonlocal seq
        seq += 1
        now = time.monotonic()
        age = min(1.0, max(0.0, timing.currentTime - timing.inputBufferAdcTime))
        item = (seq, now - age, indata.copy())
        try:
            blocks.put_nowait(item)
        except queue.Full:
            try:
                blocks.get_nowait()
                dropped["audio"] += 1
                blocks.put_nowait(item)
            except queue.Empty:
                pass

    def committed(seg: Segment) -> list[str]:
        return [word for frag in seg.fragments for word in frag.english]

    def enqueue(seg: Segment, english: list[str], context: str) -> None:
        if not english:
            return
        with cv:
            purge_obsolete_jobs()
            if len(jobs) >= 12:
                dropped["translation"] += 1
                emit("translation_skipped", {"id": seg.id, "reason": "queue full; stopping to avoid lost words"})
                raise RuntimeError("Translation queue full; session stopped to avoid losing words")
            frag = Fragment(seg.revision + 1, english, context, time.monotonic())
            seg.fragments.append(frag)
            seg.revision += 1
            revision = seg.revision
            jobs.append((seg, frag))
            cv.notify()
            queue_len = len(jobs)
        trace(seg, "queued", fragment_id=frag.id, revision=revision, queue_size=queue_len)
        emit("coverage", {"id": seg.id, "fragment_id": frag.id, "words": len(english),
                          "queue_size": queue_len})

    def invalidate_from(seg: Segment, hypothesis: list[str]) -> None:
        with cv:
            matched = common(committed(seg), hypothesis)
            if matched == len(committed(seg)):
                return
            keep = 0
            covered = 0
            for frag in seg.fragments:
                covered += len(frag.english)
                if covered > matched:
                    break
                keep += 1
            seg.fragments = seg.fragments[:keep]
            seg.revision += 1
            seg.corrections += 1
            revision = seg.revision
            purge_obsolete_jobs()
            surviving_vi = " ".join(f.vietnamese for f in seg.fragments if f.vietnamese).strip()
        emit("translation_revision", {"id": seg.id, "revision": revision, "preview": surviving_vi})

    def maybe_finalize(seg: Segment, reconciled_text: str | None = None) -> None:
        with cv:
            if (seg.finished or seg.final_english is None or not seg.fragments
                    or any(frag.status != "done" for frag in seg.fragments)):
                return
            seg.finished = True
            result = reconciled_text if reconciled_text is not None else " ".join(
                frag.vietnamese for frag in seg.fragments
            ).strip()
            revision = seg.revision
            first_received = seg.first_vi_token_received_at
            covered = len(committed(seg))
            total = len(tokens(seg.final_english))
            fragments_count = len(seg.fragments)
            corrections = seg.corrections
        if result:
            trace(seg, "final_vi")
            emit("coverage_final", {"id": seg.id, "english_words": total,
                                    "covered_words": covered, "fragments": fragments_count,
                                    "revisions": corrections})
            emit("vietnamese_final", {"id": seg.id, "text": result, "revision": revision,
                                       "first_token_received_latency": (first_received - seg.started) if first_received else None,
                                       "first_token_latency": (first_received - seg.started) if first_received else None,
                                       "latency": time.monotonic() - seg.started})

    def asr_worker() -> None:
        audio: deque[np.ndarray] = deque()
        samples = 0
        active = False
        seg: Segment | None = None
        last_voice = 0.0
        last_decode = 0.0
        decoded_samples = 0
        last_voiced_sample = 0
        decoded_voiced_sample = 0
        number = 0
        last_seq = 0
        rate = cfg.input_rate

        def decode(final: bool) -> None:
            nonlocal last_decode, decoded_samples, decoded_voiced_sample
            assert seg is not None
            if samples < int(0.45 * rate):
                return
            if final and seg.previous and last_voiced_sample <= decoded_voiced_sample:
                text = seg.previous
            else:
                signal = np.concatenate(tuple(audio))[-int(7 * rate):]
                pcm = scipy.signal.resample_poly(signal, core.ASR_RATE, rate).astype(np.float32)
                text = core.transcribe(pcm, cfg.whisper_path).strip()
            now = time.monotonic()
            last_decode = now
            decoded_samples = samples
            decoded_voiced_sample = last_voiced_sample
            if not text or text.casefold() in {"[music]", "(music)"}:
                return
            if seg.first_en_at is None:
                seg.first_en_at = now
                trace(seg, "first_en_ready")
            current = tokens(text)
            if final:
                trace(seg, "final_en")
                emit("english_final", {"id": seg.id, "text": text,
                                       "latency": now - seg.started})
                invalidate_from(seg, current)
                with cv:
                    committed_words = committed(seg)
                    remainder = current[len(committed_words):]
                    context = " ".join(committed_words[-12:])
                    seg.final_english = text
                    frag = None
                    # Latency/throughput optimization: coalesce into single queued fragment if awaiting start
                    if remainder and len(seg.fragments) == 1 and seg.fragments[0].status == "queued":
                        seg.fragments[0].english = current
                        seg.revision += 1
                        revision = seg.revision
                        purge_obsolete_jobs()
                        queue_len = len(jobs)
                        frag = seg.fragments[0]
                    elif remainder:
                        purge_obsolete_jobs()
                        if len(jobs) >= 12:
                            dropped["translation"] += 1
                            emit("translation_skipped", {"id": seg.id, "reason": "queue full; stopping to avoid lost words"})
                            raise RuntimeError("Translation queue full; session stopped to avoid losing words")
                        frag = Fragment(seg.revision + 1, remainder, context, time.monotonic())
                        seg.fragments.append(frag)
                        seg.revision += 1
                        revision = seg.revision
                        jobs.append((seg, frag))
                        cv.notify()
                        queue_len = len(jobs)
                if frag and frag.status == "queued" and frag in jobs:
                    trace(seg, "queued", fragment_id=frag.id, revision=revision, queue_size=queue_len)
                    emit("coverage", {"id": seg.id, "fragment_id": frag.id, "words": len(remainder),
                                      "queue_size": queue_len})
                elif not remainder:
                    maybe_finalize(seg)
                return

            previous = tokens(seg.previous)
            stable_count = common(previous, current)
            stable_words = current[:stable_count]
            stable_text = " ".join(stable_words)
            if stable_text and stable_text != seg.stable:
                seg.stable_since = seg.previous_at
                seg.stable_en_at = now
                trace(seg, "stable")
            seg.stable = stable_text
            seg.previous = text
            seg.previous_at = now
            emit("english_partial", {"id": seg.id, "text": text, "stable": stable_text,
                                     "latency": now - seg.started})
            invalidate_from(seg, current)
            with cv:
                prefix = committed(seg)
            pending = stable_words[len(prefix):]
            if len(pending) < 4:
                return
            cut = min(len(pending), 8)
            boundaries = [i + 1 for i, word in enumerate(pending[:cut])
                          if i >= 3 and word.endswith((",", ";", ":", ".", "?", "!"))]
            if boundaries:
                cut = boundaries[-1]
            elif cut == len(pending) and not pending[-1].endswith((".", "?", "!")):
                cut -= 1
            while cut > 0 and key(pending[cut - 1]) in UNSAFE_ENDINGS:
                cut -= 1
            candidate = pending[:cut]
            if len(candidate) >= 4 and len({key(word) for word in candidate}) >= 3:
                trace(seg, "eligible", stable_wait=now - seg.stable_since)
                enqueue(seg, candidate, " ".join(prefix[-12:]))

        while not stop.is_set():
            try:
                current_seq, stamp, block = blocks.get(timeout=0.2)
            except queue.Empty:
                continue
            if last_seq and current_seq != last_seq + 1:
                if seg and seg.previous:
                    emit("translation_skipped", {"id": seg.id, "reason": "audio overflow"})
                    with cv:
                        seg.fragments.clear()
                        seg.revision += 1
                        purge_obsolete_jobs()
                    emit("vietnamese_cancelled", {"id": seg.id})
                audio.clear()
                samples = 0
                active = False
                seg = None
                decoded_samples = last_voiced_sample = decoded_voiced_sample = 0
            last_seq = current_seq
            mono = block.mean(axis=1).astype(np.float32)
            rms = float(np.sqrt(np.mean(np.square(mono, dtype=np.float64))))
            voiced = math.isfinite(rms) and rms >= cfg.min_rms
            if voiced and not active:
                active = True
                number += 1
                seg = Segment(number, stamp)
                last_decode = stamp
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
                samples = 0
                active = False
                seg = None
                decoded_samples = last_voiced_sample = decoded_voiced_sample = 0

    def translation_worker() -> None:
        while not stop.is_set():
            with cv:
                while not stop.is_set() and not jobs:
                    cv.wait(timeout=0.2)
                if stop.is_set():
                    break
                seg, frag = jobs.pop(0)
                valid = frag in seg.fragments and not seg.finished
            if not valid:
                dropped["translation"] += 1
                emit("translation_skipped", {"id": seg.id, "reason": "obsolete fragment"})
                continue

            now = time.monotonic()
            frag.dequeued_at = now
            wait = now - frag.queued_at
            trace(seg, "dequeued", fragment_id=frag.id, queue_wait=wait)
            if wait > cfg.max_lag:
                emit("translation_delayed", {"id": seg.id, "wait": wait})
            with cv:
                frag.status = "translating"

            class Cancelled:
                def is_set(self) -> bool:
                    with cv:
                        return stop.is_set() or frag not in seg.fragments

            cancel = Cancelled()
            last_update = 0.0

            def request_start() -> None:
                frag.request_start_at = time.monotonic()
                trace(seg, "request_start", fragment_id=frag.id)

            def token(text: str) -> None:
                nonlocal last_update
                t_now = time.monotonic()
                with cv:
                    if frag not in seg.fragments:
                        return
                    first = seg.first_vi_token_received_at is None
                    if first:
                        seg.first_vi_token_received_at = t_now
                    if not frag.first_token_at:
                        frag.first_token_at = t_now
                    previous_vi = " ".join(item.vietnamese for item in seg.fragments
                                           if item is not frag and item.status == "done")
                    revision = seg.revision
                if first:
                    trace(seg, "first_token_received", fragment_id=frag.id)
                if first or t_now - last_update >= 0.05:
                    preview = " ".join(part for part in (previous_vi, text) if part).strip()
                    emit("vietnamese_partial", {"id": seg.id, "fragment_id": frag.id, "text": preview,
                         "revision": revision, "latency": t_now - seg.started, "received_at": t_now})
                    last_update = t_now

            req_start = time.monotonic()
            result = core.translate_stream(
                " ".join(frag.english), cfg.translation_model, token, cancel,
                on_request_start=request_start,
                on_stats=lambda stats: emit("ollama_stats", {"id": seg.id,
                    "fragment_id": frag.id,
                    "load_ms": stats.get("load_duration", 0) / 1_000_000,
                    "prompt_ms": stats.get("prompt_eval_duration", 0) / 1_000_000,
                    "eval_ms": stats.get("eval_duration", 0) / 1_000_000}),
                context=frag.context)
            done_time = time.monotonic()
            frag.done_at = done_time
            with cv:
                if frag not in seg.fragments or stop.is_set():
                    dropped["translation"] += 1
                    continue
                frag.vietnamese = result
                frag.status = "done"
                preview = " ".join(item.vietnamese for item in seg.fragments if item.vietnamese)
                revision = seg.revision
            trace(seg, "translation_done", fragment_id=frag.id,
                  request_duration=done_time - (frag.request_start_at or req_start))
            emit("vietnamese_partial", {"id": seg.id, "fragment_id": frag.id, "text": preview.strip(),
                 "revision": revision,
                 "latency": (seg.first_vi_token_received_at or done_time) - seg.started,
                 "received_at": done_time})

            # Selective lightweight reconciliation:
            # Check if all fragments are done and if boundaries across fragments require reconciliation
            with cv:
                all_done = (seg.final_english is not None and seg.fragments
                            and all(f.status == "done" for f in seg.fragments)
                            and not seg.finished)
                should_reconcile = False
                if all_done and len(seg.fragments) > 1 and not seg.reconciled:
                    for i in range(len(seg.fragments) - 1):
                        if is_risky_boundary(seg.fragments[i].english, seg.fragments[i + 1].english):
                            should_reconcile = True
                            break

            if should_reconcile:
                trace(seg, "reconciliation_start")
                reconcile_start = time.monotonic()
                try:
                    reconciled = core.translate_stream(
                        seg.final_english, cfg.translation_model,
                        on_token=lambda t: None,
                        stop=cancel,
                        on_request_start=lambda: None,
                        context=""
                    )
                    trace(seg, "reconciliation_done", duration=time.monotonic() - reconcile_start)
                    with cv:
                        seg.reconciled = True
                    maybe_finalize(seg, reconciled_text=reconciled)
                except Exception as exc:
                    trace(seg, "reconciliation_failed", error=str(exc))
                    maybe_finalize(seg)
            else:
                maybe_finalize(seg)

    def guarded(name: str, work: Callable[[], None]) -> None:
        try:
            work()
        except Exception as exc:
            errors.put(RuntimeError(f"{name}: {exc}"))
            stop.set()
            with cv:
                cv.notify_all()

    workers = [threading.Thread(target=guarded, args=("ASR", asr_worker), daemon=True),
               threading.Thread(target=guarded, args=("translation", translation_worker), daemon=True)]
    for worker in workers:
        worker.start()
    emit("status", {"text": "Listening — original audio remains audible"})
    try:
        with sd.InputStream(device=cfg.input_device, samplerate=cfg.input_rate, channels=2,
                            dtype="float32", blocksize=int(cfg.input_rate * 0.02),
                            callback=capture) as stream:
            next_health = time.monotonic() + 5
            while not stop.wait(0.2):
                if not stream.active:
                    raise RuntimeError("BlackHole capture stopped")
                if core.device_identity(cfg.output_device) != cfg.output_identity:
                    raise RuntimeError("Headphone output changed; restart")
                if time.monotonic() >= next_health:
                    with cv:
                        backlog = len(jobs)
                    emit("health", {"dropped": dropped.copy(), "translation_backlog": backlog})
                    next_health = time.monotonic() + 5
        if not errors.empty():
            raise errors.get_nowait()
    finally:
        stop.set()
        with cv:
            cv.notify_all()
        for worker in workers:
            worker.join(timeout=1)
