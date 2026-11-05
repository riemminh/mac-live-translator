"""Session context tracking state, memory, cards, and pending segments for Visual Understanding."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any

from mac_live_translator.context_service.fts_store import SessionFTSStore
from mac_live_translator.context_service.models import BatchClaim, MeaningCard
from mac_live_translator.meeting.context import MeetingContextStore
from mac_live_translator.meeting.memory_models import MeetingMemory, MemoryItem
from mac_live_translator.meeting.memory_store import CompactedMemoryStore


class SessionContext:
    """Encapsulates in-memory storage, cards, and atomic claiming for one active meeting session."""

    def __init__(
        self,
        session_id: str,
        context_store: MeetingContextStore | None = None,
        memory_store: CompactedMemoryStore | None = None,
    ) -> None:
        self.session_id = session_id
        self.generation_id = 1
        self.created_at = time.time()
        self.lock = threading.Lock()

        # Shared or session-scoped storage components
        self.fts_store = SessionFTSStore(max_segments=2000)
        self.context_store = context_store or MeetingContextStore(max_entries=1500)
        self.memory_store = memory_store or CompactedMemoryStore(protect_recent=25)

        # Feed & Visual state
        self.current_topic = "Đang xác định chủ đề…"
        self.pinned_question: str | None = None
        self.cards: OrderedDict[int, MeaningCard] = OrderedDict()
        self.decisions: list[dict[str, Any]] = []
        self.action_items: list[dict[str, Any]] = []
        self.next_card_id = 1

        # Batching, concurrency & timing
        self.analyzed_segment_ids: set[int] = set()
        self.pending_segment_ids: list[int] = []
        self.last_analysis_attempt_time = 0.0
        self.batch_start_monotonic = 0.0
        self.is_analyzing = False
        self.active_claim_id = 0
        self.cloud_opt_in = False

    def reset(self) -> None:
        """Reset session state and advance generation to invalidate in-flight results."""
        with self.lock:
            self.generation_id += 1
            self.fts_store.clear()
            self.context_store.clear()
            self.memory_store.clear()
            self.current_topic = "Đang xác định chủ đề…"
            self.pinned_question = None
            self.cards.clear()
            self.decisions.clear()
            self.action_items.clear()
            self.analyzed_segment_ids.clear()
            self.pending_segment_ids.clear()
            self.last_analysis_attempt_time = 0.0
            self.batch_start_monotonic = 0.0
            self.is_analyzing = False
            self.active_claim_id = 0

    def ingest_segment(self, segment_id: int, text: str, is_filler: bool = False) -> bool:
        """Idempotently ingest a finalized English segment and track pending batch timing."""
        with self.lock:
            added = self.fts_store.add_segment(segment_id, text, is_filler)
            if added:
                self.context_store.add_segment(segment_id, text, is_filler)
                if segment_id not in self.analyzed_segment_ids and segment_id not in self.pending_segment_ids:
                    self.pending_segment_ids.append(segment_id)
                    if self.batch_start_monotonic == 0.0:
                        self.batch_start_monotonic = time.monotonic()
            return added

    def claim_pending_batch(
        self,
        min_size: int = 5,
        max_size: int = 8,
        min_interval: float = 15.0,
        force: bool = False,
    ) -> BatchClaim | None:
        """Atomically claim an eligible batch under lock, setting is_analyzing to prevent races."""
        with self.lock:
            if self.is_analyzing or not self.pending_segment_ids:
                return None
            now = time.monotonic()
            if self.last_analysis_attempt_time > 0 and (now - self.last_analysis_attempt_time) < min_interval:
                return None

            elapsed = (now - self.batch_start_monotonic) if self.batch_start_monotonic > 0 else 0.0
            eligible = force or (len(self.pending_segment_ids) >= min_size) or (
                elapsed >= 25.0 and len(self.pending_segment_ids) >= 3
            )
            if not eligible:
                return None

            batch_ids = list(self.pending_segment_ids[:max_size])
            self.is_analyzing = True
            self.last_analysis_attempt_time = now
            self.active_claim_id += 1
            return BatchClaim(
                session_id=self.session_id,
                generation_id=self.generation_id,
                batch_ids=batch_ids,
                claim_id=self.active_claim_id,
                created_at=now,
            )

    def release_claim(self, claim: BatchClaim) -> None:
        """Release claim on failure/cancellation without advancing analyzed checkpoints."""
        with self.lock:
            if claim.claim_id == self.active_claim_id and claim.generation_id == self.generation_id:
                self.is_analyzing = False

    def commit_analysis(
        self,
        claim: BatchClaim,
        topic: str,
        pinned_question: str | None,
        new_cards: list[MeaningCard],
        decisions: list[dict[str, Any]],
        proposals: list[dict[str, Any]],
        action_items: list[dict[str, Any]],
        open_questions: list[dict[str, Any]],
        key_facts: list[dict[str, Any]],
        overview: str = "",
    ) -> bool:
        """Commit validated analysis results atomically if generation is still active."""
        with self.lock:
            if claim.generation_id != self.generation_id or claim.claim_id != self.active_claim_id:
                return False  # Discard stale or superseded request

            self.current_topic = topic
            self.pinned_question = pinned_question
            for cid in claim.batch_ids:
                self.analyzed_segment_ids.add(cid)
            self.pending_segment_ids = [pid for pid in self.pending_segment_ids if pid not in self.analyzed_segment_ids]
            self.batch_start_monotonic = time.monotonic() if self.pending_segment_ids else 0.0
            self.is_analyzing = False

            # Append unique cards
            for c in new_cards:
                self.cards[c.card_id] = c
                self.next_card_id = max(self.next_card_id, c.card_id + 1)
            while len(self.cards) > 200:
                self.cards.popitem(last=False)

            if decisions:
                self.decisions = (decisions + self.decisions)[:15]
            if action_items:
                self.action_items = (action_items + self.action_items)[:15]

            # Merge all semantic categories into CompactedMemoryStore
            current_mem = self.memory_store.get_memory()
            u_dec = [MemoryItem(text=d["text"], source_ids=d.get("source_ids", []), status="confirmed") for d in decisions]
            u_prop = [MemoryItem(text=p["text"], source_ids=p.get("source_ids", []), status="proposed") for p in proposals]
            u_act = [
                MemoryItem(
                    text=a["text"], source_ids=a.get("source_ids", []),
                    owner=a.get("owner", ""), deadline=a.get("deadline", ""),
                    status=a.get("status", "confirmed"),
                ) for a in action_items
            ]
            u_q = [MemoryItem(text=q["text"], source_ids=q.get("source_ids", [])) for q in open_questions]
            u_facts = [MemoryItem(text=f["text"], source_ids=f.get("source_ids", [])) for f in key_facts]

            merged_mem = MeetingMemory(
                overview=overview or current_mem.overview,
                topics=current_mem.topics,
                decisions=(u_dec + current_mem.decisions)[:25],
                proposals=(u_prop + current_mem.proposals)[:25],
                action_items=(u_act + current_mem.action_items)[:25],
                open_questions=(u_q + current_mem.open_questions)[:25],
                risks_blockers=current_mem.risks_blockers,
                key_facts=(u_facts + current_mem.key_facts)[:25],
                last_compacted_id=max(claim.batch_ids) if claim.batch_ids else current_mem.last_compacted_id,
                compaction_version=current_mem.compaction_version + 1,
            )
            self.memory_store.commit_compaction(
                session_id=self.memory_store.get_session_id(),
                new_memory=merged_mem,
                max_batch_id=max(claim.batch_ids) if claim.batch_ids else 0,
            )
            return True
