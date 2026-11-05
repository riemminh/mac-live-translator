"""Bounded in-memory store for meeting transcripts and chronological context."""

from __future__ import annotations

import re
import threading
import time
from collections import OrderedDict

from mac_live_translator.meeting.models import TranscriptEntry
from mac_live_translator.meeting.retrieval import format_transcript_for_prompt, tokenize_query


class MeetingContextStore:
    """Thread-safe, bounded in-memory store for meeting transcript segments."""

    def __init__(self, max_entries: int = 1500) -> None:
        self._max_entries = max_entries
        self._entries: OrderedDict[int, TranscriptEntry] = OrderedDict()
        self._lock = threading.Lock()
        self._session_start_monotonic = time.monotonic()
        self._session_start_wall = time.time()

    def clear(self) -> None:
        """Reset the context store for a new meeting session."""
        with self._lock:
            self._entries.clear()
            self._session_start_monotonic = time.monotonic()
            self._session_start_wall = time.time()

    def add_segment(self, segment_id: int, text: str, is_filler: bool = False) -> None:
        """Add or update a finalized English segment in the store."""
        cleaned = text.strip()
        if not cleaned:
            return
        now_mono = time.monotonic()
        now_wall = time.time()
        entry = TranscriptEntry(
            id=segment_id,
            text=cleaned,
            monotonic_at=now_mono,
            wall_at=now_wall,
            is_filler=is_filler,
        )
        with self._lock:
            if segment_id in self._entries:
                del self._entries[segment_id]
            self._entries[segment_id] = entry
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def get_all_entries(self) -> list[TranscriptEntry]:
        """Return an immutable snapshot of all current transcript entries in chronological order."""
        with self._lock:
            return list(self._entries.values())

    def get_recent_snapshot(self, seconds: float = 180.0, max_segments: int = 35) -> list[TranscriptEntry]:
        """Get finalized segments from approximately the last N seconds (default 3 minutes)."""
        now = time.monotonic()
        cutoff = now - seconds
        with self._lock:
            recent = [e for e in self._entries.values() if e.monotonic_at >= cutoff]
            if len(recent) > max_segments:
                recent = recent[-max_segments:]
            elif not recent and self._entries:
                recent = list(self._entries.values())[-max_segments:]
            return recent

    def search_relevant(
        self,
        query: str,
        top_k: int = 6,
        include_neighbors: bool = True,
        exclude_ids: set[int] | None = None,
    ) -> list[TranscriptEntry]:
        """Deterministic keyword search over transcript history with neighbor context."""
        keywords = tokenize_query(query)
        if not keywords:
            return []

        with self._lock:
            entries = list(self._entries.values())

        if not entries:
            return []

        excluded = exclude_ids or set()
        id_to_idx = {entry.id: idx for idx, entry in enumerate(entries)}
        id_to_entry = {entry.id: entry for entry in entries}
        scores: list[tuple[float, int]] = []

        for entry in entries:
            if entry.id in excluded:
                continue
            entry_words = {w.casefold() for w in re.findall(r"\b[A-Za-z0-9_+#.-]+\b", entry.text)}
            matched = keywords.intersection(entry_words)
            if matched:
                score = len(matched)
                if any(k.isupper() or len(k) > 4 for k in matched):
                    score += 0.5
                scores.append((score, entry.id))

        scores.sort(key=lambda x: x[0], reverse=True)
        top_ids = [seg_id for _, seg_id in scores[:top_k]]

        if not include_neighbors:
            return [id_to_entry[i] for i in sorted(top_ids) if i in id_to_entry]

        result_indices: set[int] = set()
        for seg_id in top_ids:
            if seg_id in id_to_idx:
                idx = id_to_idx[seg_id]
                result_indices.add(idx)
                if idx > 0:
                    result_indices.add(idx - 1)
                if idx + 1 < len(entries):
                    result_indices.add(idx + 1)

        sorted_indices = sorted(result_indices)
        return [entries[i] for i in sorted_indices]

    def get_context_summary(self) -> dict:
        """Return summary statistics of the meeting context store."""
        with self._lock:
            total_entries = len(self._entries)
            words = sum(len(e.text.split()) for e in self._entries.values())
            latest_id = next(reversed(self._entries)) if self._entries else None
            duration = (time.monotonic() - self._session_start_monotonic) if total_entries else 0.0
            return {
                "total_segments": total_entries,
                "total_words": words,
                "latest_id": latest_id,
                "duration_seconds": duration,
            }

    @staticmethod
    def format_for_prompt(entries: list[TranscriptEntry], unconfirmed_text: str = "") -> str:
        """Format transcript entries into prompt string."""
        return format_transcript_for_prompt(entries, unconfirmed_text)

