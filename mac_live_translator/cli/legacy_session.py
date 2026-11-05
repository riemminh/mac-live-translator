"""Optional legacy CLI fixed-chunk pipeline coordinator with spoken TTS output."""

from __future__ import annotations

import queue
import threading
import time
from typing import Callable

import numpy as np
import sounddevice as sd

from mac_live_translator.asr.whisper import ASR_RATE, prepare_whisper, transcribe
from mac_live_translator.audio.devices import device_identity
from mac_live_translator.audio.routing import RESTORE, check_route
from mac_live_translator.cli.legacy_workers import (
    LegacySegment,
    LegacySpeech,
    make_inference_worker,
    make_segment_worker,
    make_tts_worker,
)
from mac_live_translator.config import Config
from mac_live_translator.translation.ollama import check_ollama, translate


def run_legacy_cli(
    cfg: Config,
    on_event: Callable[[str, dict], None] | None = None,
    external_stop: threading.Event | None = None,
) -> None:
    """Run legacy fixed-chunk capture and synchronous/spoken interpretation loop."""
    check_route(cfg)
    check_ollama(cfg.translation_model)
    print("Loading cached Whisper model and warming local Ollama...", flush=True)
    prepare_whisper(cfg.whisper_model)
    transcribe(np.zeros(ASR_RATE, dtype=np.float32), cfg.whisper_model)
    translate("Hello.", cfg.translation_model)
    print(f"Input: {cfg.input_name} | Output: {cfg.output_name} | Voice: {cfg.voice or 'off'}")
    print(f"ASR: {cfg.whisper_model} | Translation: {cfg.translation_model}")
    print(f"Fixed chunks: {cfg.chunk_seconds:g}s | stale limit: {cfg.max_lag:g}s")
    print("Capture started. Text mode keeps original audio audible through your Multi-Output Device.", flush=True)

    stop = external_stop or threading.Event()
    emit = on_event or (lambda kind, data: None)
    blocks: queue.Queue[tuple[int, np.ndarray]] = queue.Queue(maxsize=32)
    segments: queue.Queue[LegacySegment] = queue.Queue(maxsize=2)
    speech: queue.Queue[LegacySpeech] = queue.Queue(maxsize=2)
    dropped = {"audio": 0, "segment": 0, "speech": 0, "stale": 0, "capture_status": 0}
    errors: queue.Queue[str] = queue.Queue()
    sequence = 0

    def callback(indata: np.ndarray, frames: int, timing: object, status: sd.CallbackFlags) -> None:
        nonlocal sequence
        sequence += 1
        if status:
            dropped["capture_status"] += 1
        try:
            blocks.put_nowait((sequence, indata.copy()))
        except queue.Full:
            try:
                blocks.get_nowait()
                dropped["audio"] += 1
            except queue.Empty:
                pass
            try:
                blocks.put_nowait((sequence, indata.copy()))
            except queue.Full:
                dropped["audio"] += 1

    def guarded_worker(name: str, fn: Callable[[], None]) -> None:
        try:
            fn()
        except Exception as exc:
            errors.put(f"{name} worker stopped: {exc}")
            stop.set()

    workers = [
        threading.Thread(
            target=guarded_worker,
            args=("segment", make_segment_worker(cfg, stop, blocks, segments, dropped)),
            name="segmenter",
            daemon=True,
        ),
        threading.Thread(
            target=guarded_worker,
            args=("inference", make_inference_worker(cfg, stop, segments, speech, dropped, errors, emit)),
            name="inference",
            daemon=True,
        ),
    ]
    if cfg.speak:
        workers.append(
            threading.Thread(
                target=guarded_worker,
                args=("TTS", make_tts_worker(cfg, stop, speech, dropped, errors)),
                name="tts",
                daemon=True,
            )
        )
    for worker in workers:
        worker.start()

    try:
        with sd.InputStream(
            device=cfg.input_device,
            samplerate=cfg.sample_rate,
            channels=2,
            dtype="float32",
            callback=callback,
        ) as stream:
            next_health = time.monotonic() + 10
            while not stop.wait(0.2):
                if not stream.active:
                    raise RuntimeError("BlackHole input stream stopped.")
                if device_identity(cfg.output_device) != cfg.output_identity:
                    raise RuntimeError("Headphone output disconnected or changed.")
                if time.monotonic() >= next_health:
                    print(
                        f"[HEALTH] queues audio={blocks.qsize()} segment={segments.qsize()} speech={speech.qsize()} dropped={dropped}",
                        flush=True,
                    )
                    emit("health", {"dropped": dropped.copy(), "queues": (blocks.qsize(), segments.qsize(), speech.qsize())})
                    next_health = time.monotonic() + 10
        if not errors.empty():
            raise RuntimeError(errors.get_nowait())
    except KeyboardInterrupt:
        print("Stopping...", flush=True)
    finally:
        stop.set()
        sd.stop()
        for worker in workers:
            worker.join(timeout=1)
        print(RESTORE, flush=True)
