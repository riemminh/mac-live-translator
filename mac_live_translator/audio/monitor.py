"""Diagnostic input audio monitor measuring RMS and peak levels."""

from __future__ import annotations

import queue
import time
import numpy as np
import sounddevice as sd

from mac_live_translator.audio.devices import check_input
from mac_live_translator.audio.routing import RESTORE


def monitor_input(index: int, name: str, rate: int) -> None:
    """Print real-time RMS and peak audio levels from the selected input device without recording."""
    check_input(index, name, rate)
    levels: queue.Queue[tuple[float, float]] = queue.Queue(maxsize=4)

    def callback(indata: np.ndarray, frames: int, timing: object, status: sd.CallbackFlags) -> None:
        sample = indata.copy()
        rms = float(np.sqrt(np.mean(np.square(sample, dtype=np.float64))))
        peak = float(np.max(np.abs(sample)))
        try:
            levels.put_nowait((rms, peak))
        except queue.Full:
            pass

    print(f"Monitoring {name} (RMS/peak only). Play YouTube; Ctrl+C stops. {RESTORE}", flush=True)
    last_print = 0.0
    try:
        with sd.InputStream(device=index, channels=2, samplerate=rate, dtype="float32", callback=callback):
            while True:
                try:
                    rms, peak = levels.get(timeout=2)
                    if time.monotonic() - last_print >= 0.5:
                        print(f"RMS {rms:.4f}  peak {peak:.4f}", flush=True)
                        last_print = time.monotonic()
                except queue.Empty:
                    print("No input buffers received. Check BlackHole and macOS input permission.", flush=True)
    except KeyboardInterrupt:
        print(RESTORE)

