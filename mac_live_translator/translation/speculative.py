"""Fast speculative candidate selection and rate limiting for early Vietnamese preview."""

from __future__ import annotations

from mac_live_translator.asr.stability import key
from mac_live_translator.translation.models import Segment
from mac_live_translator.translation.policy import UNSAFE_ENDINGS, is_filler


def select_speculative_candidate(
    seg: Segment,
    current_tokens: list[str],
    committed_words: list[str],
    last_candidate: list[str],
    last_candidate_at: float,
    now: float,
    cooldown: float = 0.35,
    min_words: int = 4,
    max_words: int = 10,
) -> list[str] | None:
    """Select a clean, meaningful uncommitted English span for speculative preview."""
    if seg.finished or seg.final_english is not None:
        return None
    uncommitted = current_tokens[len(committed_words):]
    if len(uncommitted) < min_words:
        return None
    if is_filler(uncommitted):
        return None

    candidate = uncommitted[:max_words]
    while len(candidate) > min_words and key(candidate[-1]) in UNSAFE_ENDINGS:
        candidate = candidate[:-1]

    if len(candidate) < min_words:
        return None
    if len({key(w) for w in candidate}) < 3:
        return None
    if candidate == last_candidate:
        return None
    if (now - last_candidate_at < cooldown) and len(candidate) <= len(last_candidate) + 1:
        return None

    return candidate

