"""Local in-memory store for meeting transcripts and chronological context."""

from __future__ import annotations

import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptEntry:
    """An immutable transcript line with monotonic and wall-clock timestamps."""
    id: int
    text: str
    monotonic_at: float
    wall_at: float
    is_filler: bool = False


STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can't", "cannot", "could", "couldn't",
    "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during",
    "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't",
    "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here",
    "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i",
    "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's",
    "its", "itself", "let's", "me", "more", "most", "mustn't", "my", "myself",
    "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought",
    "our", "ours", "ourselves", "out", "over", "own", "same", "shan't", "she",
    "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such",
    "than", "that", "that's", "the", "their", "theirs", "them", "themselves",
    "then", "there", "there's", "these", "they", "they'd", "they'll", "they're",
    "they've", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were",
    "weren't", "what", "what's", "when", "when's", "where", "where's", "which",
    "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would",
    "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours",
    "yourself", "yourselves",
}


def tokenize_query(query: str) -> set[str]:
    """Extract informative lowercase keywords from query string."""
    words = re.findall(r"\b[A-Za-z0-9_+#.-]+\b", query.casefold())
    return {w for w in words if len(w) > 1 and w not in STOPWORDS}


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
            # Maintain bounded RAM
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
                # If meeting was quiet or spaced out, return latest available
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
        scores: list[tuple[float, int]] = []

        for idx, entry in enumerate(entries):
            if entry.id in excluded:
                continue
            entry_words = {w.casefold() for w in re.findall(r"\b[A-Za-z0-9_+#.-]+\b", entry.text)}
            matched = keywords.intersection(entry_words)
            if matched:
                score = len(matched)
                # Boost if phrase or acronym match
                if any(k.isupper() or len(k) > 4 for k in matched):
                    score += 0.5
                scores.append((score, entry.id))

        scores.sort(key=lambda x: x[0], reverse=True)
        top_ids = [seg_id for _, seg_id in scores[:top_k]]

        if not include_neighbors:
            return [self._entries[i] for i in sorted(top_ids) if i in self._entries]

        # Include adjacent neighbor segments (i-1 and i+1) to provide conversational context
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
    def format_for_prompt(
        entries: list[TranscriptEntry],
        unconfirmed_text: str = "",
    ) -> str:
        """Format transcript entries into a clean prompt text with exact source citations."""
        lines = []
        for e in entries:
            filler_tag = " (filler)" if e.is_filler else ""
            lines.append(f"[T#{e.id}]{filler_tag}: {e.text}")
        if unconfirmed_text.strip():
            lines.append(f"[T#LIVE-UNCONFIRMED]: {unconfirmed_text.strip()}")
        return "\n".join(lines)

