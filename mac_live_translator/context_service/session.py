"""Session context tracking state, memory, cards, and pending segments for Visual Understanding."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any

from mac_live_translator.context_service.fts_store import SessionFTSStore
from mac_live_translator.context_service.models import MeaningCard
from mac_live_translator.meeting.context import MeetingContextStore
from mac_live_translator.meeting.memory_models import MeetingMemory, MemoryItem
from mac_live_translator.meeting.memory_store import CompactedMemoryStore


class SessionContext:
    """Encapsulates in-memory storage, cards, and state for one active meeting session."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.created_at = time.time()
        self.lock = threading.Lock()

        # Storage components
        self.fts_store = SessionFTSStore(max_segments=2000)
        self.context_store = MeetingContextStore(max_entries=1500)
        self.memory_store = CompactedMemoryStore(protect_recent=25)

        # Feed & Visual state
        self.current_topic = "Đang xác định chủ đề…"
        self.pinned_question: str | None = None
        self.cards: OrderedDict[int, MeaningCard] = OrderedDict()
        self.decisions: list[dict[str, Any]] = []
        self.action_items: list[dict[str, Any]] = []
        self.next_card_id = 1

        # Batching & analysis management
        self.analyzed_segment_ids: set[int] = set()
        self.pending_segment_ids: list[int] = []
        self.last_analysis_time = 0.0
        self.is_analyzing = False

    def ingest_segment(self, segment_id: int, text: str, is_filler: bool = False) -> bool:
        """Idempotently ingest a finalized English segment."""
        with self.lock:
            added = self.fts_store.add_segment(segment_id, text, is_filler)
            if added:
                self.context_store.add_segment(segment_id, text, is_filler)
                if segment_id not in self.analyzed_segment_ids and segment_id not in self.pending_segment_ids:
                    self.pending_segment_ids.append(segment_id)
            return added

    def get_pending_batch(self, min_size: int = 5, max_size: int = 8, min_interval: float = 15.0) -> list[int] | None:
        """Check if pending segments form an eligible batch for Claude analysis."""
        with self.lock:
            if self.is_analyzing:
                return None
            now = time.monotonic()
            if self.last_analysis_time > 0 and (now - self.last_analysis_time) < min_interval:
                return None
            if not self.pending_segment_ids:
                return None

            # Eligible if reached min_size OR enough time has passed with at least 3 segments
            elapsed = now - self.last_analysis_time if self.last_analysis_time > 0 else 999.0
            if len(self.pending_segment_ids) >= min_size or (elapsed >= 25.0 and len(self.pending_segment_ids) >= 3):
                batch_ids = self.pending_segment_ids[:max_size]
                return batch_ids
            return None

    def commit_analysis(
        self,
        batch_ids: list[int],
        topic: str,
        pinned_question: str | None,
        new_cards: list[MeaningCard],
        decisions: list[dict[str, Any]],
        action_items: list[dict[str, Any]],
        overview: str = "",
    ) -> None:
        """Atomically commit analysis results and advance state."""
        with self.lock:
            self.current_topic = topic
            self.pinned_question = pinned_question
            for cid in batch_ids:
                self.analyzed_segment_ids.add(cid)
            self.pending_segment_ids = [pid for pid in self.pending_segment_ids if pid not in self.analyzed_segment_ids]
            self.last_analysis_time = time.monotonic()
            self.is_analyzing = False

            for c in new_cards:
                self.cards[c.card_id] = c
                self.next_card_id = max(self.next_card_id, c.card_id + 1)
            while len(self.cards) > 200:
                self.cards.popitem(last=False)

            if decisions:
                self.decisions = (decisions + self.decisions)[:15]
            if action_items:
                self.action_items = (action_items + self.action_items)[:15]

            # Sync with CompactedMemoryStore
            current_mem = self.memory_store.get_memory()
            updated_decisions = [MemoryItem(text=d["text"], source_ids=d.get("source_ids", [])) for d in decisions]
            updated_actions = [
                MemoryItem(
                    text=a["text"],
                    source_ids=a.get("source_ids", []),
                    owner=a.get("owner", ""),
                    deadline=a.get("deadline", ""),
                    status=a.get("status", "confirmed"),
                ) for a in action_items
            ]
            merged_mem = MeetingMemory(
                overview=overview or current_mem.overview,
                topics=current_mem.topics,
                decisions=updated_decisions + current_mem.decisions,
                proposals=current_mem.proposals,
                action_items=updated_actions + current_mem.action_items,
                open_questions=current_mem.open_questions,
                risks_blockers=current_mem.risks_blockers,
                key_facts=current_mem.key_facts,
                last_compacted_id=max(batch_ids) if batch_ids else current_mem.last_compacted_id,
                compaction_version=current_mem.compaction_version + 1,
            )
            self.memory_store.commit_compaction(
                session_id=self.memory_store.get_session_id(),
                new_memory=merged_mem,
                max_batch_id=max(batch_ids) if batch_ids else 0,
            )
