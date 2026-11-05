"""macOS speech synthesis (say) and physical headphone playback helpers."""

from __future__ import annotations

import subprocess
import tempfile
import threading
import time
from math import gcd
from pathlib import Path

import numpy as np
import scipy.signal
import sounddevice as sd
import soundfile as sf

from mac_live_translator.audio.devices import check_output, device_identity
from mac_live_translator.config import Config


def list_voices() -> list[str]:
    """Return list of installed Vietnamese macOS speech voices."""
    result = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, check=True)
    voices = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) > 1 and parts[1].lower().replace("-", "_").startswith("vi_"):
            voices.append(parts[0])
            print(line)
    if not voices:
        print(
            "No Vietnamese voice installed. System Settings > Accessibility > Spoken Content (or Read & Speak) > System Voice."
        )
    return voices


def choose_voice(requested: str | None) -> str:
    """Validate requested Vietnamese voice or select the default installed voice."""
    voices = list_voices()
    if requested and requested.casefold() not in {v.casefold() for v in voices}:
        raise ValueError(f"'{requested}' is not an installed Vietnamese voice.")
    if not voices:
        raise ValueError("Install a Vietnamese macOS voice before spoken translation.")
    return requested or voices[0]


def tts_audio(text: str, voice: str) -> tuple[np.ndarray, int]:
    """Generate temporary AIFF audio via macOS `say` and decode into float32 PCM."""
    with tempfile.TemporaryDirectory(prefix="voice-translator-") as directory:
        path = Path(directory) / "speech.aiff"
        result = subprocess.run(
            ["say", "-v", voice, "-o", str(path), "--", text],
            capture_output=True,
            text=True,
            timeout=45,
        )
        if result.returncode:
            raise RuntimeError(f"macOS say failed: {result.stderr.strip()}")
        return sf.read(path, dtype="float32", always_2d=True)


def play_audio(text: str, cfg: Config, stop: threading.Event | None = None) -> float:
    """Synthesize text and play audio directly to the physical output device."""
    if device_identity(cfg.output_device) != cfg.output_identity:
        raise RuntimeError("Headphone device changed. Stop and reselect --output-device.")

    target_rate = check_output(cfg.output_device, cfg.output_name)
    audio, source_rate = tts_audio(text, cfg.voice)
    channels = min(2, int(sd.query_devices(cfg.output_device)["max_output_channels"]))

    if channels == 1:
        audio = audio.mean(axis=1, keepdims=True)
    elif audio.shape[1] == 1:
        audio = np.repeat(audio, 2, axis=1)
    else:
        audio = audio[:, :2]

    if source_rate != target_rate:
        factor = gcd(source_rate, target_rate)
        audio = scipy.signal.resample_poly(
            audio, target_rate // factor, source_rate // factor, axis=0
        ).astype(np.float32)

    sd.play(audio, samplerate=target_rate, device=cfg.output_device, blocking=False)
    started = time.monotonic()
    while sd.get_stream().active:
        if stop and stop.wait(0.1):
            sd.stop()
            break
        time.sleep(0.05)

    return time.monotonic() - started

