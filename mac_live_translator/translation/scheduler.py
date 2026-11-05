"""Priority scheduling, job queues, revision invalidation, and speculative coordination."""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable

from mac_live_translator.asr.stability import common, tokens
from mac_live_translator.pipeline.metrics import trace
from mac_live_translator.translation.models import Fragment, Segment, SpeculativeJob


class TranslationScheduler:
    """Coordinates high-priority live fragments, speculative preview, and reconciliation jobs."""

    def __init__(self, lock: threading.Lock, cv: threading.Condition) -> None:
        self.lock = lock
        self.cv = cv
        self.high_jobs: list[tuple[Segment, Fragment]] = []
        self.low_jobs: list[tuple[Segment, str, float]] = []
        self.speculative_job: SpeculativeJob | None = None
        self.active_speculative_cancel: threading.Event | None = None
        self.active_speaking: bool = False

    def cancel_speculative(self) -> None:
        """Immediately abort any active speculative inference and drop pending candidates."""
        if self.active_speculative_cancel is not None:
            self.active_speculative_cancel.set()
        self.speculative_job = None

    def set_speculative(self, seg: Segment, english: list[str], context: str) -> None:
        """Schedule a provisional speculative preview job if live queue is not overloaded."""
        with self.cv:
            if len(self.high_jobs) > 0 or len(self.low_jobs) >= 8 or seg.finished:
                self.cancel_speculative()
                return
            if self.active_speculative_cancel is not None:
                self.active_speculative_cancel.set()
            self.speculative_job = SpeculativeJob(
                segment_id=seg.id,
                revision=seg.revision,
                english=english,
                context=context,
                created_at=time.monotonic(),
            )
            self.cv.notify()

    def purge_obsolete_jobs(self) -> None:
        """Prune jobs whose fragments or segments were cancelled or finished."""
        self.high_jobs = [(s, f) for s, f in self.high_jobs if f in s.fragments and not s.finished]
        self.low_jobs = [(s, t, q) for s, t, q in self.low_jobs if not s.finished]
        if self.speculative_job and self.speculative_job.segment_id:
            for s, _ in self.high_jobs:
                if s.id == self.speculative_job.segment_id and s.finished:
                    self.speculative_job = None
                    break

    @staticmethod
    def committed_words(seg: Segment) -> list[str]:
        """Return all English words currently committed across completed or queued fragments."""
        return [word for frag in seg.fragments for word in frag.english]

    @staticmethod
    def build_context(recent_final_en: deque[str], prefix_words: list[str]) -> str:
        """Compose rolling context from recent finalized sentences and earlier fragment words."""
        parts: list[str] = []
        for past_sent in recent_final_en:
            parts.extend(tokens(past_sent))
        parts.extend(prefix_words)
        return " ".join(parts[-28:])

    def enqueue(
        self,
        seg: Segment,
        english: list[str],
        context: str,
        dropped: dict[str, int],
        emit: Callable[[str, dict], None],
    ) -> None:
        """Queue a new high-priority translation fragment for processing."""
        if not english:
            return
        with self.cv:
            self.cancel_speculative()
            self.purge_obsolete_jobs()
            if len(self.high_jobs) + len(self.low_jobs) >= 16:
                dropped["translation"] += 1
                emit("translation_skipped", {"id": seg.id, "reason": "queue full; stopping to avoid lost words"})
                raise RuntimeError("Translation queue full; session stopped to avoid losing words")
            frag = Fragment(seg.revision + 1, english, context, time.monotonic())
            seg.fragments.append(frag)
            seg.revision += 1
            revision = seg.revision
            self.high_jobs.append((seg, frag))
            self.cv.notify()
            queue_len = len(self.high_jobs)
        trace(emit, seg, "queued", fragment_id=frag.id, revision=revision, queue_size=queue_len)
        emit("coverage", {"id": seg.id, "fragment_id": frag.id, "words": len(english), "queue_size": queue_len})

    def invalidate_from(
        self,
        seg: Segment,
        hypothesis: list[str],
        emit: Callable[[str, dict], None],
    ) -> None:
        """Truncate invalidated fragments when newer ASR hypothesis corrects earlier words."""
        with self.cv:
            self.cancel_speculative()
            matched = common(self.committed_words(seg), hypothesis)
            if matched == len(self.committed_words(seg)):
                return
            keep = 0
            covered = 0
            for frag in seg.fragments:
                covered += len(frag.english)
                if covered > matched:
                    break
                keep += 1
            seg.fragments = seg.fragments[:keep]
            seg.revision += 1
            seg.corrections += 1
            revision = seg.revision
            self.purge_obsolete_jobs()
            surviving_vi = " ".join(f.vietnamese for f in seg.fragments if f.vietnamese).strip()
        emit("translation_revision", {"id": seg.id, "revision": revision, "preview": surviving_vi})
