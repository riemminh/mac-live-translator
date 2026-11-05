"""Audio device enumeration, resolution, identity, and output validation."""

from __future__ import annotations

import sounddevice as sd


def devices() -> list[dict]:
    """Return all available audio devices from sounddevice."""
    return list(sd.query_devices())


def list_devices() -> None:
    """Print formatted list of detected audio devices and routing reminders."""
    default_output = sd.default.device[1]
    print("Audio devices (* = current macOS/PortAudio default output):")
    for i, dev in enumerate(devices()):
        directions = []
        if dev["max_input_channels"]:
            directions.append(f"in {dev['max_input_channels']}ch")
        if dev["max_output_channels"]:
            directions.append(f"out {dev['max_output_channels']}ch")
        print(f"{'*' if i == default_output else ' '} {i:>3} {dev['name']} ({', '.join(directions)})")
    print("Text mode: set macOS output to a Multi-Output Device containing BlackHole and headphones.")
    print("Optional spoken replacement: set macOS output to BlackHole 2ch.")


def resolve_device(value: str, direction: str) -> tuple[int, str]:
    """Find a unique device matching index or case-insensitive name fragment."""
    found = []
    key = "max_input_channels" if direction == "input" else "max_output_channels"
    numeric = value.isdecimal()
    for i, dev in enumerate(devices()):
        if dev[key] and (i == int(value) if numeric else value.casefold() in dev["name"].casefold()):
            found.append((i, dev["name"]))
    if len(found) != 1:
        raise ValueError(
            f"Expected one {direction} device for '{value}', found {found or 'none'}. Run --list-devices."
        )
    return found[0]


def device_identity(index: int) -> tuple:
    """Generate a stable fingerprint tuple for an audio device index."""
    dev = sd.query_devices(index)
    host = sd.query_hostapis(dev["hostapi"])["name"]
    return (
        dev["name"],
        host,
        int(dev["max_input_channels"]),
        int(dev["max_output_channels"]),
        int(dev["default_samplerate"]),
    )


def check_input(index: int, name: str, rate: int) -> None:
    """Validate that the input device is BlackHole 2ch and accepts input settings."""
    if "blackhole 2ch" not in name.casefold():
        raise ValueError(f"Input must be BlackHole 2ch, got '{name}'.")
    sd.check_input_settings(device=index, channels=2, samplerate=rate, dtype="float32")


def check_output(index: int, name: str) -> int:
    """Ensure the output device is physical (not virtual loopback) and accepts playback settings."""
    lowered = name.casefold()
    if any(word in lowered for word in ("blackhole", "multi-output", "aggregate", "soundflower", "loopback")):
        raise ValueError(f"'{name}' is a virtual/combined output. Select physical headphones.")
    dev = sd.query_devices(index)
    if dev["max_output_channels"] < 1:
        raise ValueError(f"'{name}' has no output channels.")
    rate = int(dev["default_samplerate"])
    sd.check_output_settings(
        device=index,
        channels=min(2, int(dev["max_output_channels"])),
        samplerate=rate,
        dtype="float32",
    )
    return rate

