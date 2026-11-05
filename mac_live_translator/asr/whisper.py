"""MLX Whisper model preparation and local speech transcription wrapper."""

from __future__ import annotations

import re
from pathlib import Path
import numpy as np

ASR_RATE = 16_000


def prepare_whisper(repo: str) -> str:
    """Return local directory path or verify downloaded HuggingFace snapshot."""
    if Path(repo).is_dir():
        return repo
    from huggingface_hub import snapshot_download
    try:
        return snapshot_download(repo_id=repo, local_files_only=True)
    except Exception as exc:
        raise RuntimeError(
            f"Whisper model is not cached: {repo}. Download it during setup; see README.md. ({exc})"
        ) from exc


def transcribe(audio: np.ndarray, model_path: str) -> str:
    """Execute local English ASR with MLX Whisper without conditioning on previous text."""
    import mlx_whisper
    result = mlx_whisper.transcribe(
        audio,
        path_or_hf_repo=model_path,
        language="en",
        condition_on_previous_text=False,
        temperature=0.0,
        verbose=None,
    )
    return re.sub(r"\s+", " ", str(result.get("text", ""))).strip()

