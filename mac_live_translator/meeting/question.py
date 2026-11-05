"""Deterministic multi-segment question reconstruction for fragmented ASR."""

from __future__ import annotations

import re

from mac_live_translator.meeting.models import DetectedQuestion, TranscriptEntry

QUESTION_STARTERS = {
    "what", "how", "why", "when", "where", "who", "whom", "whose", "which",
    "can", "could", "would", "should", "is", "are", "was", "were",
    "do", "does", "did", "has", "have", "had", "will", "shall", "may", "might",
}

QUESTION_PHRASES = (
    "what do you think", "what are your thoughts", "how about", "what about",
    "any thoughts", "anyone know", "any update", "do we know",
)

NON_QUESTION_TAGS = {
    "right?", "yeah?", "ok?", "okay?", "huh?", "uh-huh?", "yep?", "sure?",
}


def _starts_with_question_cue(text: str) -> bool:
    """Check if normalized text begins with a question starter word or phrase."""
    cleaned = text.strip().casefold()
    if any(cleaned.startswith(p) for p in QUESTION_PHRASES):
        return True
    first_word = re.split(r"\W+", cleaned)[0] if cleaned else ""
    return first_word in QUESTION_STARTERS


def _join_segments(segments: list[TranscriptEntry]) -> str:
    """Join transcript segment texts naturally without inventing missing words."""
    result = ""
    for seg in segments:
        txt = seg.text.strip()
        if not txt:
            continue
        if not result:
            result = txt
            continue
        prev_has_punct = result[-1] in ".!?,:;"
        next_is_vocative = bool(re.match(r"^[A-Z][a-z]+\??$", txt)) and len(txt.split()) == 1
        if not prev_has_punct and next_is_vocative:
            result = f"{result}, {txt}"
        elif prev_has_punct:
            result = f"{result} {txt}"
        else:
            result = f"{result} {txt}"
    return result.strip()


def _is_standalone_complete(text: str) -> bool:
    """Determine if a single segment ending in ? is a standalone complete question."""
    cleaned = text.strip()
    if not cleaned.endswith("?"):
        return False
    if cleaned.casefold() in NON_QUESTION_TAGS:
        return False
    words = cleaned.split()
    if len(words) < 3:
        return False
    return _starts_with_question_cue(cleaned)


def reconstruct_question_from_segments(
    segments: list[TranscriptEntry],
    max_lookback: int = 15,
    max_time_gap: float = 6.0,
) -> DetectedQuestion | None:
    """Detect and reconstruct the most recent meaningful question from transcript segments."""
    valid = [s for s in segments if not s.is_filler and s.text.strip()]
    if not valid:
        return None

    recent_window = valid[-max_lookback:]
    n = len(recent_window)

    for i in range(n - 1, -1, -1):
        target = recent_window[i]
        text_i = target.text.strip()

        if text_i.endswith("?"):
            if text_i.casefold() in NON_QUESTION_TAGS and i == 0:
                continue

            if _is_standalone_complete(text_i):
                return DetectedQuestion(
                    text=text_i,
                    source_ids=[target.id],
                    confidence=1.0,
                )

            # Look backwards to find question opening
            for j in range(i - 1, max(-1, i - 5), -1):
                prev_seg = recent_window[j]
                if max_time_gap > 0 and (recent_window[j + 1].monotonic_at - prev_seg.monotonic_at) > max_time_gap:
                    break

                # If previous segment terminated an earlier sentence, stop before it
                candidate_slice = recent_window[j : i + 1]
                joined = _join_segments(candidate_slice)

                if _starts_with_question_cue(joined):
                    words = joined.split()
                    if len(words) >= 3:
                        return DetectedQuestion(
                            text=joined,
                            source_ids=[s.id for s in candidate_slice],
                            confidence=0.95,
                        )

                if prev_seg.text.strip().endswith((".", "!")):
                    break

    # Secondary check: recent segment starting with clear question phrase without trailing '?'
    for i in range(n - 1, -1, -1):
        seg = recent_window[i]
        txt = seg.text.strip()
        if _starts_with_question_cue(txt) and len(txt.split()) >= 4:
            # Check if there is an immediate continuation
            slice_end = i + 1
            if i + 1 < n and not txt.endswith((".", "!")):
                next_seg = recent_window[i + 1]
                if (next_seg.monotonic_at - seg.monotonic_at) <= max_time_gap:
                    slice_end = i + 2
            candidate_slice = recent_window[i:slice_end]
            joined = _join_segments(candidate_slice)
            if not joined.endswith("?"):
                joined = joined.rstrip(".!, ") + "?"
            return DetectedQuestion(
                text=joined,
                source_ids=[s.id for s in candidate_slice],
                confidence=0.85,
            )

    return None

