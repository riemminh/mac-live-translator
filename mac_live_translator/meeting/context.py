"""Bounded in-memory store for meeting transcripts and chronological context."""

from __future__ import annotations

import re
import threading
import time
from collections import OrderedDict

from mac_live_translator.meeting.models import DetectedQuestion, TranscriptEntry
from mac_live_translator.meeting.question import reconstruct_question_from_segments
from mac_live_translator.meeting.retrieval import (
    extract_topic_keywords,
    format_transcript_for_prompt,
)


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
        entry = TranscriptEntry(
            id=segment_id,
            text=cleaned,
            monotonic_at=time.monotonic(),
            wall_at=time.time(),
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

    def detect_recent_question(self, max_segments: int = 15) -> DetectedQuestion | None:
        """Detect and reconstruct the most recent question within finalized segments."""
        with self._lock:
            recent = list(self._entries.values())[-max_segments:]
        return reconstruct_question_from_segments(recent)

    def search_relevant(
        self,
        query: str,
        top_k: int = 4,
        include_neighbors: bool = True,
        exclude_ids: set[int] | None = None,
        max_words: int = 350,
    ) -> list[TranscriptEntry]:
        """Deterministic keyword search over older transcript history with neighbor context."""
        keywords = extract_topic_keywords(query)
        if not keywords:
            return []

        with self._lock:
            entries = list(self._entries.values())

        if not entries:
            return []

        excluded = exclude_ids or set()
        id_to_idx = {entry.id: idx for idx, entry in enumerate(entries)}
        scores: list[tuple[float, int]] = []

        for entry in entries:
            if entry.id in excluded or entry.is_filler:
                continue
            entry_words = {w.casefold() for w in re.findall(r"\b[A-Za-z0-9_+#.-]+\b", entry.text)}
            matched = keywords.intersection(entry_words)
            if not matched:
                continue

            # Require multi-word match if query has multiple keywords, unless matching a salient term
            has_salient = any(len(k) >= 5 or any(c.isupper() for c in k) for k in matched)
            if len(keywords) >= 2 and len(matched) < 2 and not has_salient:
                continue

            score = len(matched) * 1.5 + (1.0 if has_salient else 0.0)
            scores.append((score, entry.id))

        scores.sort(key=lambda x: x[0], reverse=True)
        top_ids = [seg_id for _, seg_id in scores[:top_k]]
        if not top_ids:
            return []

        result_indices: set[int] = set()
        for seg_id in top_ids:
            idx = id_to_idx[seg_id]
            result_indices.add(idx)
            if include_neighbors:
                if idx > 0 and entries[idx - 1].id not in excluded:
                    result_indices.add(idx - 1)
                if idx + 1 < len(entries) and entries[idx + 1].id not in excluded:
                    result_indices.add(idx + 1)

        sorted_entries = [entries[i] for i in sorted(result_indices)]
        # Bound by max_words budget
        budgeted: list[TranscriptEntry] = []
        word_count = 0
        for entry in sorted_entries:
            cnt = len(entry.text.split())
            if word_count + cnt > max_words and budgeted:
                break
            budgeted.append(entry)
            word_count += cnt

        return sorted(budgeted, key=lambda e: e.id)

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
