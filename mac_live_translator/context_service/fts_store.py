"""Session-scoped in-memory SQLite FTS5 index for finalized English meeting transcripts."""

from __future__ import annotations

import re
import sqlite3
import threading
import time
from mac_live_translator.context_service.models import SearchResult, TranscriptSegment


class SessionFTSStore:
    """Thread-safe SQLite FTS5 index for finalized transcript segments."""

    def __init__(self, max_segments: int = 2000) -> None:
        self._max_segments = max_segments
        self._lock = threading.Lock()
        self._db: sqlite3.Connection | None = None
        self._segments: dict[int, TranscriptSegment] = {}
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            if self._db is not None:
                try:
                    self._db.close()
                except Exception:
                    pass
            self._db = sqlite3.connect(":memory:", check_same_thread=False)
            self._db.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS transcript_fts USING fts5(
                    segment_id UNINDEXED,
                    text,
                    is_filler UNINDEXED,
                    created_at UNINDEXED,
                    tokenize='porter unicode61'
                )
                """
            )
            self._segments.clear()

    def clear(self) -> None:
        """Reset the FTS store and memory structures."""
        self._init_db()

    def add_segment(self, segment_id: int, text: str, is_filler: bool = False) -> bool:
        """Insert or replace a finalized English segment idempotently."""
        cleaned = text.strip()
        if not cleaned:
            return False

        seg = TranscriptSegment(
            segment_id=segment_id,
            text=cleaned,
            is_filler=is_filler,
            wall_at=time.time(),
        )

        with self._lock:
            if self._db is None:
                return False
            # Idempotency: remove previous row if existing
            if segment_id in self._segments:
                self._db.execute("DELETE FROM transcript_fts WHERE segment_id = ?", (str(segment_id),))

            self._segments[segment_id] = seg
            self._db.execute(
                "INSERT INTO transcript_fts(segment_id, text, is_filler, created_at) VALUES (?, ?, ?, ?)",
                (str(seg.segment_id), seg.text, 1 if seg.is_filler else 0, seg.wall_at),
            )
            self._db.commit()

            # Evict oldest if exceeding max_segments
            if len(self._segments) > self._max_segments:
                oldest_id = next(iter(self._segments))
                del self._segments[oldest_id]
                self._db.execute("DELETE FROM transcript_fts WHERE segment_id = ?", (str(oldest_id),))
                self._db.commit()
            return True

    def get_segment(self, segment_id: int) -> TranscriptSegment | None:
        """Fetch a segment by ID to verify raw evidence provenance."""
        with self._lock:
            return self._segments.get(segment_id)

    def get_all_segments(self) -> list[TranscriptSegment]:
        """Return all stored segments in chronological order."""
        with self._lock:
            return list(self._segments.values())

    def get_total_count(self) -> int:
        """Return total number of segments in store."""
        with self._lock:
            return len(self._segments)

    def search(self, query: str, top_k: int = 6, exclude_filler: bool = True) -> list[SearchResult]:
        """Full-text search over finalized transcript segments using SQLite FTS5."""
        sanitized_tokens = [re.sub(r'[^A-Za-z0-9_+#.-]', '', t).strip() for t in query.split()]
        valid_tokens = [f'"{t}"*' for t in sanitized_tokens if len(t) >= 2]
        if not valid_tokens:
            return []

        match_clause = " OR ".join(valid_tokens[:8])
        results: list[SearchResult] = []

        with self._lock:
            if not self._db or not self._segments:
                return []
            try:
                cursor = self._db.execute(
                    """
                    SELECT segment_id, text, created_at, rank
                    FROM transcript_fts
                    WHERE transcript_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (match_clause, top_k * 2),
                )
                rows = cursor.fetchall()
            except sqlite3.OperationalError:
                return []

            for raw_id, text, wall_at, rank_score in rows:
                seg_id = int(raw_id)
                seg = self._segments.get(seg_id)
                if seg and exclude_filler and seg.is_filler:
                    continue
                results.append(
                    SearchResult(
                        segment_id=seg_id,
                        text=text,
                        wall_at=float(wall_at),
                        score=abs(float(rank_score)),
                    )
                )
                if len(results) >= top_k:
                    break

        return results
