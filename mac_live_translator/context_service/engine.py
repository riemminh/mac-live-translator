"""Core Meeting Context Engine coordinating storage, FTS5 retrieval, and single-pass analysis."""

from __future__ import annotations

import threading
import uuid
from typing import Any

from mac_live_translator.context_service.analyzer import (
    SinglePassAnalysisResult,
    execute_single_pass_analysis,
)
from mac_live_translator.context_service.models import (
    CatchupData,
    MeaningCard,
    SearchResult,
    UnderstandingFeed,
)
from mac_live_translator.context_service.session import SessionContext
from mac_live_translator.copilot.client import ClaudeClient


class ContextEngine:
    """Thread-safe engine managing meeting sessions, transcript FTS5, and Claude understanding."""

    def __init__(self, client: ClaudeClient | None = None) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, SessionContext] = {}
        self.client = client or ClaudeClient()

    def create_session(self, session_id: str | None = None) -> SessionContext:
        """Create or initialize an active meeting session."""
        sid = session_id or str(uuid.uuid4())[:8]
        with self._lock:
            session = SessionContext(sid)
            self._sessions[sid] = session
            return session

    def get_or_create_session(self, session_id: str = "default") -> SessionContext:
        """Get an existing session or create it if not found."""
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionContext(session_id)
            return self._sessions[session_id]

    def get_session(self, session_id: str) -> SessionContext | None:
        """Retrieve an active session by ID."""
        with self._lock:
            return self._sessions.get(session_id)

    def delete_session(self, session_id: str) -> bool:
        """Delete an active session and purge its in-memory stores."""
        with self._lock:
            session = self._sessions.pop(session_id, None)
            if session:
                session.fts_store.clear()
                session.context_store.clear()
                session.memory_store.clear()
                return True
            return False

    def add_segment(self, session_id: str, segment_id: int, text: str, is_filler: bool = False) -> bool:
        """Add a finalized English segment to the session."""
        session = self.get_or_create_session(session_id)
        return session.ingest_segment(segment_id, text, is_filler)

    def trigger_analysis(
        self,
        session_id: str,
        force: bool = False,
        stop_event: threading.Event | None = None,
    ) -> SinglePassAnalysisResult | None:
        """Evaluate pending segments and execute single-pass Claude analysis if eligible."""
        session = self.get_session(session_id)
        if not session or not self.client.is_configured():
            return None

        batch_ids = session.get_pending_batch(min_size=1 if force else 5)
        if not batch_ids:
            return None

        # Lock analysis execution
        with session.lock:
            session.is_analyzing = True

        try:
            # Build batch text from FTS store
            batch_segs = [session.fts_store.get_segment(i) for i in batch_ids]
            valid_segs = [s for s in batch_segs if s is not None and not s.is_filler]
            if not valid_segs:
                with session.lock:
                    session.is_analyzing = False
                return None

            batch_text = "\n".join(f"[T#{s.segment_id}] {s.text}" for s in valid_segs)
            valid_ids = {s.segment_id for s in session.fts_store.get_all_segments()}

            mem_summary = session.memory_store.get_memory().format_for_prompt(max_words=300)
            if mem_summary == "No compacted historical memory available.":
                mem_summary = ""

            older_matches = session.fts_store.search(session.current_topic, top_k=3)
            older_text = "\n".join(
                f"[T#{m.segment_id}] {m.text}" for m in older_matches if m.segment_id not in batch_ids
            )

            result = execute_single_pass_analysis(
                client=self.client,
                batch_text=batch_text,
                valid_segment_ids=valid_ids,
                current_topic=session.current_topic,
                memory_summary=mem_summary,
                older_evidence=older_text,
                starting_card_id=session.next_card_id,
                stop_event=stop_event,
            )

            session.commit_analysis(
                batch_ids=batch_ids,
                topic=result.topic,
                pinned_question=result.pinned_question,
                new_cards=result.meaning_cards,
                decisions=result.decisions,
                action_items=result.action_items,
                overview=result.memory_overview,
            )
            return result
        except Exception:
            with session.lock:
                session.is_analyzing = False
            raise

    def get_feed(self, session_id: str, last_read_card_id: int = 0) -> UnderstandingFeed | None:
        """Get the current understanding feed snapshot for UI rendering."""
        session = self.get_session(session_id)
        if not session:
            return None

        with session.lock:
            all_cards = list(session.cards.values())
            recent = all_cards[-5:] if all_cards else []
            latest_id = all_cards[-1].card_id if all_cards else 0
            unread_count = sum(1 for c in all_cards if c.card_id > last_read_card_id)

            return UnderstandingFeed(
                session_id=session.session_id,
                topic=session.current_topic,
                pinned_question=session.pinned_question,
                recent_cards=recent,
                decisions=list(session.decisions[:5]),
                action_items=list(session.action_items[:5]),
                unread_count=unread_count,
                latest_card_id=latest_id,
                total_segments=session.fts_store.get_total_count(),
                total_cards=len(all_cards),
                last_analysis_at=session.last_analysis_time,
            )

    def get_catchup(self, session_id: str, last_read_card_id: int) -> CatchupData | None:
        """Generate catch-up payload for unread cards without rereading full transcript."""
        session = self.get_session(session_id)
        if not session:
            return None

        with session.lock:
            unread = [c for c in session.cards.values() if c.card_id > last_read_card_id]
            if not unread:
                return CatchupData(unread_cards=[], summary="Bạn đã theo kịp toàn bộ ý chính.", last_read_card_id=last_read_card_id, unread_count=0)

            # Build concise summary from headlines
            headlines = [c.headline for c in unread[:5]]
            summary = "Tóm lược điểm lỡ: " + " · ".join(headlines)

            return CatchupData(
                unread_cards=unread,
                summary=summary,
                last_read_card_id=unread[-1].card_id,
                unread_count=len(unread),
            )

    def search_transcript(self, session_id: str, query: str, top_k: int = 6) -> list[SearchResult]:
        """Search transcript segments in session via SQLite FTS5."""
        session = self.get_session(session_id)
        if not session:
            return []
        return session.fts_store.search(query=query, top_k=top_k)
