"""Experimental English system-audio -> Vietnamese speech translator for macOS.

Audio routing:
  Mac system output -> BlackHole 2ch (no original audio to headphones)
  Python input      <- BlackHole 2ch
  Python output     -> physical headphones, explicitly selected

This is a turn/chunk-based MVP, not simultaneous interpretation.
"""

from __future__ import annotations

import argparse
import math
import queue
import re
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import requests
import scipy.signal
import sounddevice as sd
import soundfile as sf


OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
TRANSLATION_MODEL = "translategemma:4b"
WHISPER_MODEL = "mlx-community/whisper-small.en-mlx"
ASR_SAMPLE_RATE = 16_000
DEFAULT_SAMPLE_RATE = 48_000


@dataclass(frozen=True)
class Config:
    input_device: int
    output_device: int
    input_rate: int
    chunk_seconds: float
    min_rms: float
    tts_voice: str
    text_only: bool
    whisper_model: str
    translation_model: str


def list_devices() -> None:
    print("\n=== Audio devices (use their numeric IDs) ===")
    for i, dev in enumerate(sd.query_devices()):
        labels = []
        if dev["max_input_channels"] > 0:
            labels.append(f"input {dev['max_input_channels']}ch")
        if dev["max_output_channels"] > 0:
            labels.append(f"output {dev['max_output_channels']}ch")
        print(f"{i:>3}: {dev['name']} ({', '.join(labels)})")
    print("\nImportant: output must be a physical headphone/speaker, NOT BlackHole.")


def list_voices() -> list[tuple[str, str]]:
    proc = subprocess.run(["say", "-v", "?"], text=True, capture_output=True, check=True)
    available = []
    print("\n=== Vietnamese voices available in macOS ===")
    for line in proc.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[1].lower().replace("-", "_").startswith("vi_"):
            available.append((fields[0], fields[1]))
            print(line)
    if not available:
        print("None installed. Add a Vietnamese system voice in macOS Settings > Accessibility > Spoken Content / Read & Speak > System Voice.")
    return available


def find_device(fragment: str, direction: str) -> int:
    devices = sd.query_devices()
    options: list[tuple[int, str]] = []
    max_ch = "max_input_channels" if direction == "input" else "max_output_channels"
    for i, dev in enumerate(devices):
        if dev[max_ch] > 0 and fragment.casefold() in dev["name"].casefold():
            options.append((i, dev["name"]))
    if len(options) != 1:
        matches = ", ".join(f"{i}: {name}" for i, name in options) or "none"
        raise ValueError(f"Expected one {direction} device containing '{fragment}', found {len(options)}: {matches}. Run --list-devices and use --{direction}-device <number>.")
    return options[0][0]


def resolve_device(arg: str, direction: str) -> int:
    if arg.isdecimal():
        index = int(arg)
        dev = sd.query_devices(index)
        channel_key = "max_input_channels" if direction == "input" else "max_output_channels"
        if dev[channel_key] < 1:
            raise ValueError(f"Device {index} has no {direction} channels")
        return index
    return find_device(arg, direction)


def choose_voice(requested: str | None) -> str:
    voices = list_voices()
    if requested:
        names = {v[0].lower() for v in voices}
        if requested.lower() not in names:
            raise ValueError(f"'{requested}' is not an installed Vietnamese macOS voice. Use --list-voices.")
        return requested
    if not voices:
        raise ValueError("No Vietnamese voice installed; use --list-voices for instructions.")
    return voices[0][0]


def tts_to_audio(text: str, voice: str) -> tuple[np.ndarray, int]:
    with tempfile.TemporaryDirectory(prefix="voice-translator-") as directory:
        path = Path(directory) / "speech.aiff"
        proc = subprocess.run(
            ["say", "-v", voice, "-o", str(path), "--", text],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"macOS say failed: {proc.stderr.strip()}")
        audio, sample_rate = sf.read(path, dtype="float32", always_2d=True)
        return audio, sample_rate


def play_tts(text: str, cfg: Config) -> None:
    audio, rate = tts_to_audio(text, cfg.tts_voice)
    device = sd.query_devices(cfg.output_device)
    channels = min(int(device["max_output_channels"]), 2)
    if channels == 1:
        audio = np.mean(audio, axis=1, keepdims=True)
    elif audio.shape[1] == 1:
        audio = np.repeat(audio, 2, axis=1)
    elif audio.shape[1] > 2:
        audio = audio[:, :2]
    sd.play(audio, samplerate=rate, device=cfg.output_device, blocking=True)


def translate(text: str, cfg: Config) -> str:
    prompt = (
        "Translate the following English speech into natural spoken Vietnamese. "
        "Preserve technical names. Return ONLY the Vietnamese translation; "
        "do not add notes, quotations, or English.\n\n"
        f"English: {text}"
    )
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": cfg.translation_model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0, "num_ctx": 1024, "num_predict": 160},
            "keep_alive": "10m",
        },
        timeout=90,
    )
    response.raise_for_status()
    data = response.json()
    return data["message"]["content"].strip()


def transcribe(audio: np.ndarray, cfg: Config) -> str:
    import mlx_whisper

    result = mlx_whisper.transcribe(
        audio,
        path_or_hf_repo=cfg.whisper_model,
        language="en",
        condition_on_previous_text=False,
        temperature=0.0,
        verbose=False,
    )
    return str(result.get("text", "")).strip()


def tts_worker(cfg: Config, tts_queue: "queue.Queue[str | None]") -> None:
    while True:
        text = tts_queue.get()
        try:
            if text is None:
                return
            play_tts(text, cfg)
        except Exception as exc:
            print(f"[TTS ERROR] {exc}", file=sys.stderr)
        finally:
            tts_queue.task_done()


def push_latest(tts_queue: "queue.Queue[str | None]", text: str) -> None:
    if tts_queue.full():
        try:
            discarded = tts_queue.get_nowait()
            tts_queue.task_done()
            print(f"[NOTICE] Skipped old translation due to TTS backlog: {str(discarded)[:70]}")
        except queue.Empty:
            pass
    tts_queue.put_nowait(text)


def run(cfg: Config) -> None:
    if cfg.input_device == cfg.output_device:
        raise ValueError("Input and output device must be different. Input=BlackHole, output=physical headphones.")
    input_name = sd.query_devices(cfg.input_device)["name"]
    output_name = sd.query_devices(cfg.output_device)["name"]
    if "blackhole" not in input_name.casefold():
        print(f"[WARNING] Selected input isn't named BlackHole: {input_name}")
    if "blackhole" in output_name.casefold() or "multi-output" in output_name.casefold():
        raise ValueError("Output must be actual headphones or speakers, NOT BlackHole or Multi-Output Device. This prevents audio feedback.")

    print(f"\nInput: {cfg.input_device} {input_name}")
    print(f"Output: {cfg.output_device} {output_name}")
    print(f"English STT: {cfg.whisper_model}")
    print(f"Vietnamese translation: {cfg.translation_model}")
    print(f"Vietnamese TTS: {cfg.tts_voice}")
    print("\nSET MAC SYSTEM OUTPUT TO 'BlackHole 2ch' (NOT Multi-Output Device).")
    print("This makes the original English audio silent in your headphones.")
    print("The app will play Vietnamese on the selected physical output.")
    print("Press Ctrl+C to stop. Restore macOS output manually afterward.\n")

    audio_queue: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=128)
    speech_queue: "queue.Queue[str | None]" = queue.Queue(maxsize=3)
    if not cfg.text_only:
        threading.Thread(target=tts_worker, args=(cfg, speech_queue), daemon=True).start()

    channels = min(2, int(sd.query_devices(cfg.input_device)["max_input_channels"]))

    def on_audio(indata: np.ndarray, frames: int, time_info: object, status: sd.CallbackFlags) -> None:
        if status:
            print(f"[AUDIO] {status}", file=sys.stderr)
        # PortAudio callback must stay short; all model inference runs on main thread.
        mono = np.mean(indata, axis=1).astype(np.float32, copy=False).copy()
        try:
            audio_queue.put_nowait(mono)
        except queue.Full:
            try:
                audio_queue.get_nowait()  # drop oldest audio to prevent unbounded lag
                audio_queue.task_done()
                audio_queue.put_nowait(mono)
            except queue.Empty:
                pass

    frames_needed = int(cfg.chunk_seconds * cfg.input_rate)
    audio_parts: list[np.ndarray] = []
    frames_collected = 0
    last_english = ""
    try:
        with sd.InputStream(
            device=cfg.input_device,
            samplerate=cfg.input_rate,
            channels=channels,
            dtype="float32",
            blocksize=0,
            callback=on_audio,
        ):
            while True:
                part = audio_queue.get()
                audio_queue.task_done()
                audio_parts.append(part)
                frames_collected += len(part)
                if frames_collected < frames_needed:
                    continue

                samples = np.concatenate(audio_parts)
                audio_parts.clear()
                frames_collected = 0
                rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))
                if not math.isfinite(rms) or rms < cfg.min_rms:
                    continue

                reduced = scipy.signal.resample_poly(samples, ASR_SAMPLE_RATE, cfg.input_rate).astype(np.float32)
                try:
                    english = re.sub(r"\s+", " ", transcribe(reduced, cfg)).strip()
                except Exception as exc:
                    print(f"[STT ERROR] {exc}", file=sys.stderr)
                    continue
                if not english or english.lower() == last_english.lower():
                    continue
                last_english = english
                print(f"\nEN: {english}", flush=True)
                try:
                    vietnamese = translate(english, cfg)
                except Exception as exc:
                    print(f"[TRANSLATION ERROR] {exc}", file=sys.stderr)
                    continue
                if vietnamese:
                    print(f"VI: {vietnamese}", flush=True)
                    if not cfg.text_only:
                        push_latest(speech_queue, vietnamese)
    except KeyboardInterrupt:
        print("\nStopped. Set macOS Sound Output back to your normal headphones.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline English system audio -> Vietnamese spoken translation (experimental)")
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--list-voices", action="store_true")
    parser.add_argument("--input-device", default="BlackHole 2ch", help="BlackHole input ID or name fragment")
    parser.add_argument("--output-device", help="Physical headphones output ID or name fragment")
    parser.add_argument("--sample-rate", type=int, default=DEFAULT_SAMPLE_RATE)
    parser.add_argument("--chunk-seconds", type=float, default=4.0)
    parser.add_argument("--min-rms", type=float, default=0.004)
    parser.add_argument("--voice", help="Installed macOS Vietnamese voice, e.g. Linh")
    parser.add_argument("--whisper-model", default=WHISPER_MODEL)
    parser.add_argument("--translation-model", default=TRANSLATION_MODEL)
    parser.add_argument("--text-only", action="store_true", help="Show translations but do not play Vietnamese audio")
    parser.add_argument("--test-voice", action="store_true", help="Generate a local test voice, then exit")
    args = parser.parse_args()

    if args.list_devices:
        list_devices()
        return
    if args.list_voices:
        list_voices()
        return
    if not args.output_device:
        parser.error("--output-device is required. Run --list-devices to find the numeric headphone ID")
    if not 1.0 <= args.chunk_seconds <= 15.0:
        parser.error("--chunk-seconds must be between 1 and 15")
    if args.sample_rate not in (44_100, 48_000):
        parser.error("--sample-rate must be 44100 or 48000 in this version")

    try:
        output = resolve_device(args.output_device, "output")
        voice = "" if args.text_only else choose_voice(args.voice)
        cfg = Config(
            input_device=resolve_device(args.input_device, "input"),
            output_device=output,
            input_rate=args.sample_rate,
            chunk_seconds=args.chunk_seconds,
            min_rms=args.min_rms,
            tts_voice=voice,
            text_only=args.text_only,
            whisper_model=args.whisper_model,
            translation_model=args.translation_model,
        )
        if args.test_voice:
            if args.text_only:
                parser.error("--test-voice can't be combined with --text-only")
            play_tts("Xin chào, đây là thử nghiệm phát giọng nói tiếng Việt.", cfg)
            print("Voice test complete.")
            return
        run(cfg)
    except (ValueError, RuntimeError, OSError, requests.RequestException, sd.PortAudioError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
