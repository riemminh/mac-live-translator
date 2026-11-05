"""Worker routines for legacy CLI fixed-chunk audio segmentation, inference, and TTS."""

from __future__ import annotations

import math
import queue
import threading
import time
from dataclasses import dataclass
from typing import Callable

import numpy as np
import scipy.signal

from mac_live_translator.asr.whisper import ASR_RATE, transcribe
from mac_live_translator.audio.tts import play_audio
from mac_live_translator.config import Config
from mac_live_translator.translation.ollama import translate_stream


@dataclass(frozen=True)
class LegacySegment:
    number: int
    ended: float
    audio: np.ndarray


@dataclass(frozen=True)
class LegacySpeech:
    number: int
    ended: float
    english: str
    vietnamese: str


def offer_latest(target: queue.Queue, item: object, label: str, dropped: dict[str, int]) -> None:
    """Put item into queue, discarding the oldest item if queue is full."""
    try:
        target.put_nowait(item)
    except queue.Full:
        try:
            target.get_nowait()
            dropped[label] += 1
            print(f"[DROP] {label} backlog: {dropped[label]} skipped", flush=True)
        except queue.Empty:
            pass
        try:
            target.put_nowait(item)
        except queue.Full:
            dropped[label] += 1


def make_segment_worker(
    cfg: Config,
    stop: threading.Event,
    blocks: queue.Queue[tuple[int, np.ndarray]],
    segments: queue.Queue[LegacySegment],
    dropped: dict[str, int],
) -> Callable[[], None]:
    """Return segment worker loop that slices incoming blocks into fixed-duration chunks."""
    def segment_worker() -> None:
        parts: list[np.ndarray] = []
        count = 0
        last_seq = 0
        number = 0
        target = int(cfg.chunk_seconds * cfg.sample_rate)
        while not stop.is_set():
            try:
                seq, block = blocks.get(timeout=0.2)
            except queue.Empty:
                continue
            if last_seq and seq != last_seq + 1:
                parts.clear()
                count = 0
            last_seq = seq
            parts.append(block.mean(axis=1).astype(np.float32))
            count += len(block)
            if count < target:
                continue
            samples = np.concatenate(parts)
            parts.clear()
            count = 0
            number += 1
            rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))
            if not math.isfinite(rms) or rms < cfg.min_rms:
                continue
            reduced = scipy.signal.resample_poly(samples, ASR_RATE, cfg.sample_rate).astype(np.float32)
            offer_latest(segments, LegacySegment(number, time.monotonic(), reduced), "segment", dropped)

    return segment_worker


def make_inference_worker(
    cfg: Config,
    stop: threading.Event,
    segments: queue.Queue[LegacySegment],
    speech: queue.Queue[LegacySpeech],
    dropped: dict[str, int],
    errors: queue.Queue[str],
    emit: Callable[[str, dict], None],
) -> Callable[[], None]:
    """Return inference worker loop running ASR and translation on segments."""
    def inference_worker() -> None:
        while not stop.is_set():
            try:
                item = segments.get(timeout=0.2)
            except queue.Empty:
                continue
            if time.monotonic() - item.ended > cfg.max_lag:
                dropped["stale"] += 1
                continue
            try:
                began = time.monotonic()
                english = transcribe(item.audio, cfg.whisper_model)
                if not english or english.casefold() in {"[music]", "(music)"}:
                    continue
                asr_ms = (time.monotonic() - began) * 1000
                emit("english", {"id": item.number, "text": english, "latency": time.monotonic() - item.ended})
                began = time.monotonic()
                first_token = [None]

                def on_token(text: str) -> None:
                    if first_token[0] is None:
                        first_token[0] = time.monotonic() - item.ended
                    emit("vietnamese_partial", {"id": item.number, "text": text, "latency": first_token[0]})

                vietnamese = translate_stream(english, cfg.translation_model, on_token, stop)
                translation_ms = (time.monotonic() - began) * 1000
                if not vietnamese:
                    continue
                emit("vietnamese_final", {"id": item.number, "text": vietnamese, "latency": time.monotonic() - item.ended, "first_token_latency": first_token[0]})
                print(f"#{item.number} EN: {english}")
                print(f"#{item.number} VI: {vietnamese} | ASR {asr_ms:.0f}ms, translate {translation_ms:.0f}ms, lag {time.monotonic()-item.ended:.1f}s", flush=True)
                if cfg.speak:
                    offer_latest(speech, LegacySpeech(item.number, item.ended, english, vietnamese), "speech", dropped)
            except Exception as exc:
                errors.put(f"ASR/translation failed: {exc}")
                stop.set()

    return inference_worker


def make_tts_worker(
    cfg: Config,
    stop: threading.Event,
    speech: queue.Queue[LegacySpeech],
    dropped: dict[str, int],
    errors: queue.Queue[str],
) -> Callable[[], None]:
    """Return TTS worker loop playing synthesized audio to the headphones."""
    def tts_worker() -> None:
        while not stop.is_set():
            try:
                item = speech.get(timeout=0.2)
            except queue.Empty:
                continue
            lag = time.monotonic() - item.ended
            if lag > cfg.max_lag:
                dropped["stale"] += 1
                print(f"[DROP] #{item.number} stale before speech ({lag:.1f}s)", flush=True)
                continue
            try:
                duration = play_audio(item.vietnamese, cfg, stop)
                print(f"#{item.number} spoken | start lag {lag:.1f}s, playback {duration:.1f}s", flush=True)
            except Exception as exc:
                errors.put(f"TTS/output failed: {exc}")
                stop.set()

    return tts_worker

