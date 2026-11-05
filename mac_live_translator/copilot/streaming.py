"""Streaming section parser isolating English spoken response from Claude output."""

from __future__ import annotations

import re
from typing import Callable


class StreamingSectionParser:
    """State machine parsing Claude streaming tokens to yield clean spoken English immediately."""

    def __init__(self, on_english_chunk: Callable[[str], None]) -> None:
        self._on_english_chunk = on_english_chunk
        self._state = "SEEKING_START"
        self._buffer: list[str] = []
        self._pending_suffix = ""
        self.english_finished = False

    def feed(self, token: str) -> None:
        """Process an incoming text token from the streaming API."""
        if self.english_finished or not token:
            return

        if self._state == "SEEKING_START":
            self._buffer.append(token)
            accumulated = "".join(self._buffer)

            # Match ### ENGLISH or ### ENGLISH ANSWER
            match = re.search(r"###\s*ENGLISH(?:\s+ANSWER)?\s*[\n:]*", accumulated, re.IGNORECASE)
            if match:
                self._state = "STREAMING_ENGLISH"
                after_header = accumulated[match.end():]
                if after_header:
                    self._feed_english_text(after_header)
                return

            # If output starts directly with spoken English (no markdown header)
            stripped = accumulated.strip()
            if stripped and not stripped.startswith("#") and len(stripped) >= 20:
                self._state = "STREAMING_ENGLISH"
                self._feed_english_text(accumulated)
            return

        if self._state == "STREAMING_ENGLISH":
            self._feed_english_text(token)

    def _feed_english_text(self, text: str) -> None:
        """Buffer and emit text belonging strictly to the English spoken answer."""
        combined = self._pending_suffix + text
        self._pending_suffix = ""

        # Check for next section header (e.g. \n### or ### Ý NGHĨA or ### EVIDENCE)
        next_sec_match = re.search(r"(?:\r?\n)+\s*###\s*", combined)
        if next_sec_match:
            self.english_finished = True
            self._state = "AFTER_ENGLISH"
            clean_part = combined[:next_sec_match.start()].strip()
            if clean_part:
                self._on_english_chunk(clean_part)
            return

        # Hold back trailing prefix that might become a markdown header in subsequent chunks
        # e.g., trailing '\n', '\n#', '\n##', '\n###'
        tail_match = re.search(r"(?:\r?\n)+\s*#{0,3}\s*$", combined)
        if tail_match and tail_match.start() < len(combined):
            safe_to_emit = combined[:tail_match.start()]
            self._pending_suffix = combined[tail_match.start():]
            if safe_to_emit:
                self._on_english_chunk(safe_to_emit)
            return

        if combined:
            self._on_english_chunk(combined)

    def finish(self) -> None:
        """Flush any pending non-header text at stream completion."""
        if not self.english_finished and self._state == "STREAMING_ENGLISH":
            if self._pending_suffix and not self._pending_suffix.strip().startswith("#"):
                self._on_english_chunk(self._pending_suffix)
            self._pending_suffix = ""
            self.english_finished = True
        elif self._state == "SEEKING_START" and self._buffer:
            fallback = "".join(self._buffer).strip()
            if fallback and not fallback.startswith("#"):
                self._on_english_chunk(fallback)

