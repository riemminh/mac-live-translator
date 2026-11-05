"""Configuration models, constants, and path helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Service Endpoints & Model Defaults
OLLAMA_URL = "http://127.0.0.1:11434"
WHISPER_MODEL = "mlx-community/whisper-small.en-mlx"
TRANSLATION_MODEL = "translategemma:4b"
CLAUDE_MODEL = "claude-haiku-5-5"
DEFAULT_VOICE = "Linh"

# Audio Pipeline Defaults
DEFAULT_SAMPLE_RATE = 48_000
TARGET_SAMPLE_RATE = 16_000
DEFAULT_CHUNK_SECONDS = 4.0
DEFAULT_MIN_RMS = 0.004
DEFAULT_MAX_LAG = 12.0

# Supported Document File Extensions
SUPPORTED_DOC_EXTENSIONS = {".md", ".markdown", ".txt"}


@dataclass
class Config:
    """Runtime configuration for audio capture and translation pipelines."""
    input_device: int
    input_name: str
    output_device: int
    output_name: str
    sample_rate: int = DEFAULT_SAMPLE_RATE
    chunk_seconds: float = DEFAULT_CHUNK_SECONDS
    min_rms: float = DEFAULT_MIN_RMS
    voice: str = DEFAULT_VOICE
    whisper_model: str = WHISPER_MODEL
    translation_model: str = TRANSLATION_MODEL
    speak: bool = False
    max_lag: float = DEFAULT_MAX_LAG
    output_identity: str = ""
    fast_preview: bool = True


def load_local_env() -> None:
    """Load key-value pairs from .env into os.environ if not already present."""
    import os
    for env_path in (Path(".env"), Path(__file__).resolve().parent / ".env"):
        if env_path.is_file():
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
            except Exception:
                pass


load_local_env()

