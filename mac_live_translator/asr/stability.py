"""Word tokenization, casing normalization, and common prefix calculation."""

from __future__ import annotations

import re


def tokens(text: str) -> list[str]:
    """Split text into whitespace-delimited tokens."""
    return text.split()


def key(word: str) -> str:
    """Normalize word by stripping edge punctuation and lowercasing."""
    return re.sub(r"(^[^\w]+|[^\w]+$)", "", word).casefold()


def common(a: list[str], b: list[str]) -> int:
    """Return count of leading tokens matching in normalized key representation."""
    count = 0
    for left, right in zip(a, b):
        if key(left) != key(right):
            break
        count += 1
    return count

