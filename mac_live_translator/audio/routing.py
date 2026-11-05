"""Audio route safety guards, Multi-Output verification, and loopback prevention."""

from __future__ import annotations

import sounddevice as sd

from mac_live_translator.audio.devices import check_input, check_output, device_identity
from mac_live_translator.config import Config

RESTORE = "STOP: press Ctrl+C, then System Settings > Sound > Output > select your headphones."


def is_multi_output(name: str) -> bool:
    """Return True if device name represents a macOS Multi-Output Device."""
    return "multi-output" in name.casefold()


def is_blackhole(name: str) -> bool:
    """Return True if device name is BlackHole virtual audio."""
    return "blackhole" in name.casefold()


def check_route(cfg: Config) -> None:
    """Ensure audio routing is safe, device identities match, and prevent feedback loops."""
    current_input = sd.query_devices(cfg.input_device)
    if current_input["name"] != cfg.input_name or device_identity(cfg.output_device) != cfg.output_identity:
        raise RuntimeError("Audio device indices changed. Stop, run --list-devices, and restart.")

    check_input(cfg.input_device, cfg.input_name, cfg.sample_rate)
    check_output(cfg.output_device, cfg.output_name)

    default_index = sd.default.device[1]
    default_name = sd.query_devices(default_index)["name"] if default_index >= 0 else "none"

    # In GUI text mode (or when speak=False), system default must be Multi-Output Device
    if not cfg.speak:
        if not is_multi_output(default_name):
            raise ValueError(
                f"Text mode requires a macOS Multi-Output Device containing BlackHole and headphones; "
                f"current output is '{default_name}'. Verify both devices in Audio MIDI Setup."
            )
    else:
        # In legacy spoken replacement mode, system default must be BlackHole 2ch alone
        if default_index != cfg.input_device or not is_blackhole(default_name):
            raise ValueError(
                f"Spoken replacement mode needs macOS output set to BlackHole 2ch; "
                f"current output is '{default_name}'."
            )

    if cfg.input_device == cfg.output_device:
        raise ValueError("BlackHole input and physical output must differ.")

