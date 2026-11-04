"""Low-latency text session. Audio and models never run on the Qt thread."""

from __future__ import annotations

import math
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable

import numpy as np
import scipy.signal
import sounddevice as sd

import main as core


@dataclass(frozen=True)
class Utterance:
    id: int
    started: float
    ended: float
    text: str
    final: bool
    version: int


def run(cfg: core.Config, emit: Callable[[str, dict], None], stop: threading.Event) -> None:
    core.check_route(cfg)
    core.check_ollama(cfg.translation_model)
    emit("status", {"text": "Loading local models…"})
    core.transcribe(np.zeros(core.ASR_RATE, dtype=np.float32), cfg.whisper_path)
    core.translate("Hello.", cfg.translation_model)
    if stop.is_set():
        return

    # 20 ms blocks, eight seconds maximum: a Whisper decode can take longer
    # than the old 32-block buffer without losing the next utterance.
    blocks: queue.Queue[tuple[int, float, np.ndarray]] = queue.Queue(maxsize=400)
    translations: queue.Queue[Utterance] = queue.Queue(maxsize=2)
    errors: queue.Queue[Exception] = queue.Queue()
    dropped = {"audio": 0, "translation": 0}
    seq = 0
    latest_version = 0
    latest_by_id: dict[int, int] = {}
    final_text: dict[int, str] = {}
    preview_result: dict[int, tuple[str, float | None]] = {}
    early_available: set[int] = set()

    def capture(indata: np.ndarray, frames: int, timing: object, status: sd.CallbackFlags) -> None:
        nonlocal seq
        seq += 1
        # PortAudio times share a clock; translate the first sample's ADC time
        # to the monotonic clock used for all UI and Ollama measurements.
        callback_now = time.monotonic()
        age = min(1.0, max(0.0, timing.currentTime - timing.inputBufferAdcTime))
        item = (seq, callback_now - age, indata.copy())
        try:
            blocks.put_nowait(item)
        except queue.Full:
            try:
                blocks.get_nowait()
                dropped["audio"] += 1
                blocks.put_nowait(item)
            except queue.Empty:
                pass

    def queue_translation(number: int, started: float, text: str, final: bool) -> None:
        nonlocal latest_version
        latest_version += 1
        item = Utterance(number, started, time.monotonic(), text, final, latest_version)
        latest_by_id[number] = item.version
        if not final:
            early_available.add(number)
        emit("trace", {"id": number, "stage": "eligible" if not final else "final_eligible",
                       "at": item.ended, "source_start": started})
        try:
            translations.put_nowait(item)
        except queue.Full:
            try:
                removed = translations.get_nowait()
                if not removed.final:
                    early_available.discard(removed.id)
                emit("translation_skipped", {"id": removed.id, "reason": "queue full"})
                dropped["translation"] += 1
            except queue.Empty:
                pass
            translations.put_nowait(item)
        emit("trace", {"id": number, "stage": "queued", "at": time.monotonic(),
                       "source_start": started})

    def asr_worker() -> None:
        # Overlapping windows update one current subtitle. Only a silence or
        # duration boundary commits text and submits it for translation.
        audio: deque[np.ndarray] = deque()
        samples = 0
        active = False
        start = 0.0
        last_voice = 0.0
        last_decode = 0.0
        decoded_samples = 0
        last_voiced_sample = 0
        decoded_voiced_sample = 0
        previous = ""
        stable = ""
        early_sent = ""
        first_en_emitted = False
        number = 0
        last_seq = 0
        rate = cfg.input_rate

        def decode(final: bool) -> None:
            nonlocal last_decode, previous, stable, number, early_sent, first_en_emitted
            nonlocal decoded_samples, decoded_voiced_sample
            if samples < int(0.45 * rate):
                return
            # Limit inference memory to the most recent 7 seconds. The overlap
            # between successive decodes is intentional.
            if final and previous and last_voiced_sample <= decoded_voiced_sample:
                text = previous
            else:
                signal = np.concatenate(tuple(audio))[-int(7 * rate):]
                reduced = scipy.signal.resample_poly(signal, core.ASR_RATE, rate).astype(np.float32)
                text = core.transcribe(reduced, cfg.whisper_path).strip()
            last_decode = time.monotonic()
            decoded_samples = samples
            decoded_voiced_sample = last_voiced_sample
            if not text or text.casefold() in {"[music]", "(music)"}:
                return
            if not first_en_emitted:
                emit("trace", {"id": number + 1, "stage": "first_en_ready",
                               "at": time.monotonic(), "source_start": start})
                first_en_emitted = True
            if not final:
                old_words, new_words = previous.split(), text.split()
                common = []
                for old, new in zip(old_words, new_words):
                    if old.casefold() != new.casefold():
                        break
                    common.append(new)
                stable = " ".join(common)
                previous = text
                if stable:
                    emit("trace", {"id": number + 1, "stage": "stable",
                                   "at": time.monotonic(), "source_start": start})
                emit("english_partial", {"id": number + 1, "text": text,
                                         "stable": stable, "latency": time.monotonic() - start})
                words = stable.split()
                if not early_sent and (len(words) >= 5 or
                                       (len(words) >= 4 and stable.endswith((".", "?", "!", ",", ";", ":")))):
                    early_sent = stable
                    queue_translation(number + 1, start, stable, False)
            else:
                number += 1
                final_text[number] = text
                emit("english_final", {"id": number, "text": text,
                                       "latency": time.monotonic() - start})
                emit("trace", {"id": number, "stage": "final_en",
                               "at": time.monotonic(), "source_start": start})
                if early_sent == text and (number in early_available or number in preview_result):
                    preview = preview_result.get(number)
                    if preview:
                        result, first = preview
                        emit("vietnamese_final", {"id": number, "text": result,
                                                  "first_token_latency": first,
                                                  "latency": time.monotonic() - start})
                else:
                    queue_translation(number, start, text, True)

        while not stop.is_set():
            try:
                current, stamp, block = blocks.get(timeout=0.2)
            except queue.Empty:
                continue
            if last_seq and current != last_seq + 1:
                audio.clear()
                samples = 0
                active = False
                previous = stable = ""
                early_sent = ""
                first_en_emitted = False
                decoded_samples = last_voiced_sample = decoded_voiced_sample = 0
            last_seq = current
            mono = block.mean(axis=1).astype(np.float32)
            rms = float(np.sqrt(np.mean(np.square(mono, dtype=np.float64))))
            voiced = math.isfinite(rms) and rms >= cfg.min_rms
            if voiced and not active:
                active = True
                start = stamp
                last_decode = stamp
            if not active:
                continue
            audio.append(mono)
            samples += len(mono)
            if voiced:
                last_voice = stamp + len(mono) / rate
                last_voiced_sample = samples
            now = time.monotonic()
            new_samples = samples - decoded_samples
            if (now - last_decode >= 0.75 and new_samples >= int(0.45 * rate)
                    and samples >= int(0.7 * rate) and voiced):
                decode(False)
            pause = stamp + len(mono) / rate - last_voice
            boundary = 0.55 if previous.rstrip().endswith((".", "?", "!")) else 0.85
            if (samples >= int(1.2 * rate) and pause >= boundary) or samples >= int(7 * rate):
                decode(True)
                audio.clear()
                samples = 0
                active = False
                previous = stable = ""
                early_sent = ""
                first_en_emitted = False
                decoded_samples = last_voiced_sample = decoded_voiced_sample = 0

    def translation_worker() -> None:
        while not stop.is_set():
            try:
                item = translations.get(timeout=0.2)
            except queue.Empty:
                continue
            emit("trace", {"id": item.id, "stage": "dequeued", "at": time.monotonic(),
                           "source_start": item.started})
            if time.monotonic() - item.ended > cfg.max_lag:
                dropped["translation"] += 1
                early_available.discard(item.id)
                emit("translation_skipped", {"id": item.id, "reason": "stale queue item"})
                continue
            if item.version != latest_by_id.get(item.id):
                dropped["translation"] += 1
                early_available.discard(item.id)
                emit("translation_skipped", {"id": item.id, "reason": "newer revision"})
                continue
            class Cancelled:
                def is_set(self) -> bool:
                    return stop.is_set() or item.version != latest_by_id.get(item.id)

            cancel = Cancelled()
            first = None
            last_update = 0.0
            def request_start() -> None:
                emit("trace", {"id": item.id, "stage": "request_start",
                               "at": time.monotonic(), "source_start": item.started})

            def token(text: str) -> None:
                nonlocal first, last_update
                if first is None:
                    received_at = time.monotonic()
                    first = received_at - item.started
                    emit("trace", {"id": item.id, "stage": "first_token_received",
                                   "at": received_at, "source_start": item.started})
                if time.monotonic() - last_update >= 0.05:
                    emit("vietnamese_partial", {"id": item.id, "text": text,
                                                 "latency": first,
                                                 "received_at": time.monotonic()})
                    last_update = time.monotonic()
            result = core.translate_stream(
                item.text, cfg.translation_model, token, cancel,
                on_request_start=request_start,
                on_stats=lambda stats: emit("ollama_stats", {"id": item.id,
                    "load_ms": stats.get("load_duration", 0) / 1_000_000,
                    "prompt_ms": stats.get("prompt_eval_duration", 0) / 1_000_000,
                    "eval_ms": stats.get("eval_duration", 0) / 1_000_000}),
            )
            if cancel.is_set():
                early_available.discard(item.id)
                emit("vietnamese_cancelled", {"id": item.id})
                dropped["translation"] += 1
            elif result:
                if not item.final:
                    preview_result[item.id] = (result, first)
                    early_available.discard(item.id)
                if item.final or final_text.get(item.id) == item.text:
                    emit("vietnamese_final", {"id": item.id, "text": result,
                                              "first_token_latency": first,
                                              "latency": time.monotonic() - item.started})

    def guarded(name: str, work: Callable[[], None]) -> None:
        try:
            work()
        except Exception as exc:
            errors.put(RuntimeError(f"{name}: {exc}"))
            stop.set()

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
                    emit("health", {"dropped": dropped.copy()})
                    next_health = time.monotonic() + 5
        if not errors.empty():
            raise errors.get_nowait()
    finally:
        stop.set()
        for worker in workers:
            worker.join(timeout=1)
