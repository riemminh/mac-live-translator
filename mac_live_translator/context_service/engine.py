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
    BatchClaim,
    CatchupData,
    SearchResult,
    UnderstandingFeed,
)
from mac_live_translator.context_service.session import SessionContext
from mac_live_translator.copilot.client import ClaudeClient
from mac_live_translator.meeting.context import MeetingContextStore
from mac_live_translator.meeting.memory_store import CompactedMemoryStore


class ContextEngine:
    """Thread-safe engine managing meeting sessions, transcript FTS5, and Claude understanding."""

    def __init__(
        self,
        client: ClaudeClient | None = None,
        default_context_store: MeetingContextStore | None = None,
        default_memory_store: CompactedMemoryStore | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, SessionContext] = {}
        self.client = client or ClaudeClient()
        self.default_context_store = default_context_store
        self.default_memory_store = default_memory_store
        self.cloud_opt_in = False

    def set_cloud_opt_in(self, enabled: bool) -> None:
        """Enforce service-level authorization for cloud transmission."""
        with self._lock:
            self.cloud_opt_in = enabled
            for s in self._sessions.values():
                s.cloud_opt_in = enabled

    def create_session(self, session_id: str | None = None) -> SessionContext:
        """Create or initialize an active session."""
        sid = session_id or str(uuid.uuid4())[:8]
        return self.get_or_create_session(sid)

    def get_or_create_session(self, session_id: str = "default") -> SessionContext:
        """Get an existing session or create it using shared stores."""
        with self._lock:
            if session_id not in self._sessions:
                s = SessionContext(
                    session_id=session_id,
                    context_store=self.default_context_store,
                    memory_store=self.default_memory_store,
                )
                s.cloud_opt_in = self.cloud_opt_in
                self._sessions[session_id] = s
            return self._sessions[session_id]

    def get_session(self, session_id: str) -> SessionContext | None:
        with self._lock:
            return self._sessions.get(session_id)

    def reset_session(self, session_id: str = "default") -> None:
        """Reset session and bump generation to invalidate pending background requests."""
        session = self.get_session(session_id)
        if session:
            session.reset()

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.pop(session_id, None)
            if session:
                session.reset()
                return True
            return False

    def add_segment(self, session_id: str, segment_id: int, text: str, is_filler: bool = False) -> bool:
        session = self.get_or_create_session(session_id)
        return session.ingest_segment(segment_id, text, is_filler)

    def trigger_analysis(
        self,
        session_id: str,
        force: bool = False,
        stop_event: threading.Event | None = None,
    ) -> tuple[SinglePassAnalysisResult, BatchClaim] | None:
        """Atomically claim eligible batch and execute analysis outside the lock."""
        session = self.get_session(session_id)
        if not session or not self.cloud_opt_in or not self.client.is_configured():
            return None

        claim = session.claim_pending_batch(min_size=1 if force else 5, force=force)
        if not claim:
            return None

        try:
            batch_segs = [session.fts_store.get_segment(i) for i in claim.batch_ids]
            valid_segs = [s for s in batch_segs if s is not None and not s.is_filler]
            if not valid_segs:
                session.release_claim(claim)
                return None

            batch_text = "\n".join(f"[T#{s.segment_id}] {s.text}" for s in valid_segs)
            older_matches = session.fts_store.search(session.current_topic, top_k=3)
            evidence_segs = [m for m in older_matches if m.segment_id not in claim.batch_ids]
            older_text = "\n".join(f"[T#{m.segment_id}] {m.text}" for m in evidence_segs)

            valid_ids = {s.segment_id for s in valid_segs}.union(m.segment_id for m in evidence_segs)
            mem = session.memory_store.get_memory()
            mem_summary = mem.format_for_prompt(max_words=300) if not mem.is_empty() else ""

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

            committed = session.commit_analysis(
                claim=claim,
                topic=result.topic,
                pinned_question=result.pinned_question,
                new_cards=result.meaning_cards,
                decisions=result.decisions,
                proposals=result.proposals,
                action_items=result.action_items,
                open_questions=result.open_questions,
                key_facts=result.key_facts,
                overview=result.memory_overview,
            )
            return (result, claim) if committed else None
        except Exception:
            session.release_claim(claim)
            raise

    def get_feed(self, session_id: str, last_read_card_id: int = 0) -> UnderstandingFeed | None:
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
                generation_id=session.generation_id,
                topic=session.current_topic,
                pinned_question=session.pinned_question,
                recent_cards=recent,
                decisions=list(session.decisions[:5]),
                action_items=list(session.action_items[:5]),
                unread_count=unread_count,
                latest_card_id=latest_id,
                total_segments=session.fts_store.get_total_count(),
                total_cards=len(all_cards),
                last_analysis_at=session.last_analysis_attempt_time,
            )

    def get_catchup(self, session_id: str, last_read_card_id: int, page_size: int = 5) -> CatchupData | None:
        """Deterministic paginated catch-up without silently skipping unread cards."""
        session = self.get_session(session_id)
        if not session:
            return None
        with session.lock:
            unread = [c for c in session.cards.values() if c.card_id > last_read_card_id]
            if not unread:
                return CatchupData(unread_cards=[], summary="Đã theo kịp toàn bộ ý chính.", last_read_card_id=last_read_card_id)

            page = unread[:page_size]
            new_cursor = page[-1].card_id
            remaining = len(unread) - len(page)
            summary = (
                f"Đang xem ý #{page[0].card_id}–#{page[-1].card_id} (còn {remaining} ý chưa đọc)"
                if remaining > 0 else "Đã bắt kịp toàn bộ ý chính."
            )
            return CatchupData(
                unread_cards=page, summary=summary, last_read_card_id=new_cursor,
                unread_count=len(unread), remaining_unread=remaining, has_more=(remaining > 0),
            )

    def search_transcript(self, session_id: str, query: str, top_k: int = 6) -> list[SearchResult]:
        session = self.get_session(session_id)
        return session.fts_store.search(query=query, top_k=top_k) if session else []
