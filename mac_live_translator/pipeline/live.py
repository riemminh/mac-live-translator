"""Continuous live pipeline coordinator wiring PortAudio capture, ASR, and translation workers."""

from __future__ import annotations

import queue
import threading
import time
from collections import deque
from typing import Callable

import numpy as np
import sounddevice as sd

from mac_live_translator.asr.segmentation import run_asr_worker
from mac_live_translator.asr.whisper import ASR_RATE, prepare_whisper, transcribe
from mac_live_translator.audio.devices import device_identity
from mac_live_translator.audio.routing import check_route
from mac_live_translator.config import Config
from mac_live_translator.translation.ollama import check_ollama, translate
from mac_live_translator.translation.scheduler import TranslationScheduler
from mac_live_translator.translation.worker import run_translation_worker


def run(cfg: Config, emit: Callable[[str, dict], None], stop: threading.Event) -> None:
    """Initialize audio routing, warm models, and coordinate streaming workers until stop is set."""
    check_route(cfg)
    check_ollama(cfg.translation_model)
    emit("status", {"text": "Loading local models…"})
    prepare_whisper(cfg.whisper_model)
    transcribe(np.zeros(ASR_RATE, dtype=np.float32), cfg.whisper_model)
    translate("Hello.", cfg.translation_model)
    if stop.is_set():
        return

    blocks: queue.Queue[tuple[int, float, np.ndarray]] = queue.Queue(maxsize=400)
    lock = threading.Lock()
    cv = threading.Condition(lock)
    scheduler = TranslationScheduler(lock, cv)
    errors: queue.Queue[Exception] = queue.Queue()
    dropped = {"audio": 0, "translation": 0}
    recent_final_en: deque[str] = deque(maxlen=2)
    seq = 0

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

    def guarded(name: str, work: Callable[[], None]) -> None:
        try:
            work()
        except Exception as exc:
            errors.put(RuntimeError(f"{name}: {exc}"))
            stop.set()
            with cv:
                cv.notify_all()

    workers = [
        threading.Thread(
            target=guarded,
            args=("ASR", lambda: run_asr_worker(cfg, blocks, scheduler, emit, stop, dropped, recent_final_en)),
            daemon=True,
        ),
        threading.Thread(
            target=guarded,
            args=("translation", lambda: run_translation_worker(cfg, scheduler, emit, stop, dropped, recent_final_en)),
            daemon=True,
        ),
    ]
    for worker in workers:
        worker.start()

    emit("status", {"text": "Listening — original audio remains audible"})
    try:
        with sd.InputStream(
            device=cfg.input_device,
            samplerate=cfg.sample_rate,
            channels=2,
            dtype="float32",
            blocksize=int(cfg.sample_rate * 0.02),
            callback=capture,
        ) as stream:
            next_health = time.monotonic() + 5
            while not stop.wait(0.2):
                if not stream.active:
                    raise RuntimeError("BlackHole capture stopped")
                if device_identity(cfg.output_device) != cfg.output_identity:
                    raise RuntimeError("Headphone output changed; restart")
                if time.monotonic() >= next_health:
                    with cv:
                        backlog = len(scheduler.high_jobs) + len(scheduler.low_jobs)
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

