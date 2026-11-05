"""Data models for the Visual Meeting Understanding context service."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TranscriptSegment:
    """Finalized English transcript segment."""
    segment_id: int
    text: str
    is_filler: bool = False
    wall_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class BatchClaim:
    """Atomic batch claim token for single-worker Claude analysis."""
    session_id: str
    generation_id: int
    batch_ids: list[int]
    claim_id: int
    created_at: float


@dataclass
class MeaningCard:
    """Concise meaning card representing one key discussion point in Vietnamese."""
    card_id: int
    headline: str
    bullet_points: list[str] = field(default_factory=list)
    category: str = "key_point"  # key_point, decision, proposal, question, action
    source_ids: list[int] = field(default_factory=list)
    importance: str = "normal"  # high, normal
    topic: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "card_id": self.card_id,
            "headline": self.headline,
            "bullet_points": self.bullet_points,
            "category": self.category,
            "source_ids": self.source_ids,
            "importance": self.importance,
            "topic": self.topic,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MeaningCard:
        raw_src = data.get("source_ids", [])
        src_ids = [int(x) for x in raw_src if str(x).isdigit()] if isinstance(raw_src, list) else []
        return cls(
            card_id=int(data.get("card_id", 0)),
            headline=str(data.get("headline", "")).strip(),
            bullet_points=[str(b).strip() for b in data.get("bullet_points", []) if str(b).strip()],
            category=str(data.get("category", "key_point")).strip(),
            source_ids=src_ids,
            importance=str(data.get("importance", "normal")).strip(),
            topic=str(data.get("topic", "")).strip(),
            created_at=float(data.get("created_at", time.time())),
        )


@dataclass
class UnderstandingFeed:
    """Current state of the understanding feed for the visual UI."""
    session_id: str
    generation_id: int = 1
    topic: str = "Đang xác định chủ đề…"
    pinned_question: str | None = None
    recent_cards: list[MeaningCard] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    action_items: list[dict[str, Any]] = field(default_factory=list)
    unread_count: int = 0
    latest_card_id: int = 0
    total_segments: int = 0
    total_cards: int = 0
    last_analysis_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "generation_id": self.generation_id,
            "topic": self.topic,
            "pinned_question": self.pinned_question,
            "recent_cards": [c.to_dict() for c in self.recent_cards],
            "decisions": self.decisions,
            "action_items": self.action_items,
            "unread_count": self.unread_count,
            "latest_card_id": self.latest_card_id,
            "total_segments": self.total_segments,
            "total_cards": self.total_cards,
            "last_analysis_at": self.last_analysis_at,
        }


@dataclass
class CatchupData:
    """Catch-up payload for unread meaning cards with deterministic pagination."""
    unread_cards: list[MeaningCard] = field(default_factory=list)
    summary: str = ""
    last_read_card_id: int = 0
    unread_count: int = 0
    remaining_unread: int = 0
    has_more: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "unread_cards": [c.to_dict() for c in self.unread_cards],
            "summary": self.summary,
            "last_read_card_id": self.last_read_card_id,
            "unread_count": self.unread_count,
            "remaining_unread": self.remaining_unread,
            "has_more": self.has_more,
        }


@dataclass
class UnderstandingStatus:
    """Current analysis and scheduling status for Visual Meeting Understanding."""
    cloud_opt_in: bool
    is_analyzing: bool
    pending_count: int
    meaningful_pending: int
    last_analyzed_id: int | None
    last_success_time: float
    cooldown_remaining: float
    state: str
    next_eligible_desc: str
    auto_update_enabled: bool = True
    last_error: str = ""


@dataclass
class SearchResult:
    """Transcript search match with segment metadata."""
    segment_id: int
    text: str
    wall_at: float
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "text": self.text,
            "wall_at": self.wall_at,
            "score": self.score,
        }
