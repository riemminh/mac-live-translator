"""Natural subtitle cue splitting, cue models, and bilingual presentation formatting."""

from __future__ import annotations

import re
from dataclasses import dataclass

VIETNAMESE_CONJUNCTIONS = [
    " nhưng ", " hoặc ", " và ", " bởi vì ", " nếu ", " cho nên ",
    " tuy nhiên ", " trong khi ", " để ", " rằng ", " hay ", " mà "
]


@dataclass
class SubtitleCue:
    """A short, readable unit of speech translated for live screen presentation."""
    segment_id: int
    cue_id: int
    text: str
    status: str = "draft"  # "draft" | "stable" | "final"
    english_source: str = ""
    created_at: float = 0.0


def split_into_cues(text: str, max_chars: int = 75) -> list[str]:
    """Break Vietnamese text into 1-2 line readable cues without losing words or meaning."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    cues: list[str] = []
    current = text

    while len(current) > max_chars:
        window = current[:max_chars + 1]
        split_idx = -1

        # 1. Punctuation terminators
        for punct in (". ", "? ", "! ", "… "):
            pos = window.rfind(punct)
            if pos >= int(max_chars * 0.35):
                split_idx = pos + len(punct)
                break

        # 2. Clause punctuation boundaries
        if split_idx == -1:
            for punct in ("; ", ": ", ", ", " - "):
                pos = window.rfind(punct)
                if pos >= int(max_chars * 0.35):
                    split_idx = pos + len(punct)
                    break

        # 3. Natural conjunction boundaries
        if split_idx == -1:
            for conj in VIETNAMESE_CONJUNCTIONS:
                pos = window.rfind(conj)
                if pos >= int(max_chars * 0.35):
                    split_idx = pos + 1
                    break

        # 4. Fallback to last whitespace before max_chars
        if split_idx == -1:
            pos = window.rfind(" ")
            if pos > 0:
                split_idx = pos + 1
            else:
                split_idx = max_chars

        head = current[:split_idx].strip()
        tail = current[split_idx:].strip()
        if head:
            cues.append(head)
        current = tail

    if current:
        cues.append(current)

    return cues

