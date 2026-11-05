"""Thread-safe state manager for incremental compacted meeting memory and checkpoints."""

from __future__ import annotations

import copy
import threading
from typing import TYPE_CHECKING

from mac_live_translator.meeting.memory_models import MeetingMemory
from mac_live_translator.meeting.models import TranscriptEntry

if TYPE_CHECKING:
    from mac_live_translator.meeting.context import MeetingContextStore


class CompactedMemoryStore:
    """Thread-safe store managing incremental meeting memory, versioning, and checkpoints."""

    def __init__(self, protect_recent: int = 30) -> None:
        self.protect_recent = protect_recent
        self._lock = threading.Lock()
        self._session_id = 1
        self._memory = MeetingMemory()
        self._last_compacted_id = 0
        self._compaction_version = 0
        self._in_progress = False

    def clear(self) -> None:
        """Reset the compacted memory store for a new session."""
        with self._lock:
            self._session_id += 1
            self._memory = MeetingMemory()
            self._last_compacted_id = 0
            self._compaction_version = 0
            self._in_progress = False

    def get_memory(self) -> MeetingMemory:
        """Return a safe copy of the current compacted memory snapshot."""
        with self._lock:
            return copy.deepcopy(self._memory)

    def get_session_id(self) -> int:
        """Return the current active meeting session identifier."""
        with self._lock:
            return self._session_id

    def is_in_progress(self) -> bool:
        """Return True if a compaction request is actively running."""
        with self._lock:
            return self._in_progress

    def cancel_in_progress(self) -> None:
        """Release the in-progress lock if a compaction request is canceled or fails."""
        with self._lock:
            self._in_progress = False

    def get_eligible_batch(
        self,
        context_store: MeetingContextStore,
        min_batch: int = 15,
    ) -> list[TranscriptEntry]:
        """Identify older finalized transcript segments eligible for incremental compaction."""
        all_entries = context_store.get_all_entries()
        if len(all_entries) <= self.protect_recent:
            return []

        eligible_slice = all_entries[:-self.protect_recent]
        with self._lock:
            last_id = self._last_compacted_id

        candidates = [e for e in eligible_slice if e.id > last_id and not e.is_filler]
        if min_batch > 0 and len(candidates) < min_batch:
            return []
        return candidates

    def prepare_compaction_snapshot(
        self,
        context_store: MeetingContextStore,
        min_batch: int = 15,
        force: bool = False,
    ) -> tuple[int, MeetingMemory, list[TranscriptEntry]] | None:
        """Atomically lock and snapshot current memory and eligible batch for compaction."""
        with self._lock:
            if self._in_progress:
                return None
            effective_min = 1 if force else min_batch
            all_entries = context_store.get_all_entries()
            if len(all_entries) <= self.protect_recent:
                return None
            eligible_slice = all_entries[:-self.protect_recent]
            candidates = [e for e in eligible_slice if e.id > self._last_compacted_id and not e.is_filler]
            if len(candidates) < effective_min:
                return None
            self._in_progress = True
            return (self._session_id, copy.deepcopy(self._memory), candidates)

    def commit_compaction(
        self,
        session_id: int,
        new_memory: MeetingMemory,
        max_batch_id: int,
    ) -> bool:
        """Commit an incremental compaction result atomically if session is still valid."""
        with self._lock:
            self._in_progress = False
            if session_id != self._session_id:
                return False  # Discard result from previous or reset session

            self._last_compacted_id = max(self._last_compacted_id, max_batch_id)
            self._compaction_version += 1
            new_memory.last_compacted_id = self._last_compacted_id
            new_memory.compaction_version = self._compaction_version
            self._memory = new_memory
            return True

    def get_compaction_summary(self, context_store: MeetingContextStore | None = None) -> dict:
        """Return summary statistics for UI inspection."""
        with self._lock:
            last_id = self._last_compacted_id
            version = self._compaction_version
            in_prog = self._in_progress
            is_empty = self._memory.is_empty()
            item_count = self._memory.total_items_count()

        pending_count = 0
        if context_store:
            all_entries = context_store.get_all_entries()
            if len(all_entries) > self.protect_recent:
                older = all_entries[:-self.protect_recent]
                pending_count = sum(1 for e in older if e.id > last_id and not e.is_filler)

        return {
            "last_compacted_id": last_id,
            "compaction_version": version,
            "in_progress": in_prog,
            "is_empty": is_empty,
            "item_count": item_count,
            "pending_eligible_segments": pending_count,
            "protected_recent_count": self.protect_recent,
        }

