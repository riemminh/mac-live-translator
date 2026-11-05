"""CLI argument parsing, device diagnostics, and launcher for command-line tools."""

from __future__ import annotations

import argparse
import platform
import sys

from mac_live_translator.asr.whisper import prepare_whisper
from mac_live_translator.audio.devices import check_output, device_identity, list_devices, resolve_device
from mac_live_translator.audio.monitor import monitor_input
from mac_live_translator.audio.tts import choose_voice, list_voices, play_audio
from mac_live_translator.cli.legacy_session import run_legacy_cli
from mac_live_translator.config import Config, DEFAULT_CHUNK_SECONDS, DEFAULT_MAX_LAG, DEFAULT_MIN_RMS, DEFAULT_SAMPLE_RATE, TRANSLATION_MODEL, WHISPER_MODEL


def main() -> None:
    """CLI entrypoint for audio diagnostics and legacy interpretation mode."""
    parser = argparse.ArgumentParser(description="Local English system audio to Vietnamese text (optional speech)")
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--list-voices", action="store_true")
    parser.add_argument("--monitor-input", action="store_true")
    parser.add_argument("--test-voice", action="store_true")
    parser.add_argument("--input-device", default="BlackHole 2ch")
    parser.add_argument("--output-device", help="Physical headphones ID or unique name fragment")
    parser.add_argument("--sample-rate", type=int, default=DEFAULT_SAMPLE_RATE)
    parser.add_argument("--chunk-seconds", type=float, default=DEFAULT_CHUNK_SECONDS)
    parser.add_argument("--min-rms", type=float, default=DEFAULT_MIN_RMS)
    parser.add_argument("--max-lag", type=float, default=DEFAULT_MAX_LAG)
    parser.add_argument("--voice")
    parser.add_argument("--whisper-model", default=WHISPER_MODEL)
    parser.add_argument("--translation-model", default=TRANSLATION_MODEL)
    parser.add_argument("--speak", action="store_true", help="Optional legacy Vietnamese TTS replacement mode")
    args = parser.parse_args()

    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RuntimeError("This CLI requires an Apple Silicon Mac.")
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError("Use arm64 Python 3.12 for this project.")

    if args.list_devices:
        list_devices()
        return
    if args.list_voices:
        list_voices()
        return

    if args.sample_rate not in (44_100, 48_000) or not 1 <= args.chunk_seconds <= 15 or not 0 <= args.min_rms < 1 or not 1 <= args.max_lag <= 60:
        raise ValueError("Use --sample-rate 44100/48000, --chunk-seconds 1..15, --min-rms 0..<1, --max-lag 1..60.")

    if args.monitor_input:
        index, name = resolve_device(args.input_device, "input")
        monitor_input(index, name, args.sample_rate)
        return

    if not args.output_device:
        parser.error("--output-device is required. Run --list-devices.")

    output, output_name = resolve_device(args.output_device, "output")
    check_output(output, output_name)
    voice = choose_voice(args.voice)
    output_ident = device_identity(output)

    cfg = Config(
        input_device=-1,
        input_name="",
        output_device=output,
        output_name=output_name,
        sample_rate=args.sample_rate,
        chunk_seconds=args.chunk_seconds,
        min_rms=args.min_rms,
        voice=voice,
        whisper_model=prepare_whisper(args.whisper_model),
        translation_model=args.translation_model,
        speak=args.speak,
        max_lag=args.max_lag,
        output_identity=output_ident,
    )

    if args.test_voice:
        print(f"Testing Vietnamese voice '{voice}' through {output_name}...")
        play_audio("Xin chào. Đây là âm thanh thử nghiệm.", cfg)
        return

    input_index, input_name = resolve_device(args.input_device, "input")
    cfg.input_device = input_index
    cfg.input_name = input_name

    run_legacy_cli(cfg)

