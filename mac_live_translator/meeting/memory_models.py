"""Data models for structured, incremental compacted meeting memory."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MemoryItem:
    """A single factual statement with source transcript provenance and status."""
    text: str
    source_ids: list[int] = field(default_factory=list)
    status: str = "confirmed"  # "proposed", "confirmed", "unclear"
    owner: str = ""
    deadline: str = ""

    def format_line(self) -> str:
        """Format item with source provenance and metadata."""
        src_tag = f" [T#{', T#'.join(str(i) for i in self.source_ids)}]" if self.source_ids else ""
        meta_parts = []
        if self.owner:
            meta_parts.append(f"Owner: {self.owner}")
        if self.deadline:
            meta_parts.append(f"Deadline: {self.deadline}")
        if self.status and self.status != "confirmed":
            meta_parts.append(f"Status: {self.status}")
        meta_str = f" ({'; '.join(meta_parts)})" if meta_parts else ""
        return f"• {self.text}{meta_str}{src_tag}"


@dataclass
class MeetingMemory:
    """Consolidated semantic representation of older meeting discussions."""
    overview: str = ""
    topics: list[MemoryItem] = field(default_factory=list)
    decisions: list[MemoryItem] = field(default_factory=list)
    proposals: list[MemoryItem] = field(default_factory=list)
    action_items: list[MemoryItem] = field(default_factory=list)
    open_questions: list[MemoryItem] = field(default_factory=list)
    risks_blockers: list[MemoryItem] = field(default_factory=list)
    key_facts: list[MemoryItem] = field(default_factory=list)
    last_compacted_id: int = 0
    compaction_version: int = 0
    updated_at: float = 0.0

    def is_empty(self) -> bool:
        """Return True if memory holds no substantive summary or items."""
        return not (
            self.overview or self.topics or self.decisions or self.proposals or
            self.action_items or self.open_questions or self.risks_blockers or self.key_facts
        )

    def total_items_count(self) -> int:
        """Return total count of structured memory items across all categories."""
        return len(self.all_items())

    def all_items(self) -> list[MemoryItem]:
        """Return flat list of all memory items across categories."""
        return (
            self.topics + self.decisions + self.proposals +
            self.action_items + self.open_questions +
            self.risks_blockers + self.key_facts
        )

    def format_for_prompt(self, max_words: int = 450) -> str:
        """Format compacted memory for Claude prompt within strict token/word bounds."""
        if self.is_empty():
            return "No compacted historical memory available."
        lines: list[str] = []
        if self.overview:
            lines.append(f"Meeting Overview:\n{self.overview}\n")

        sections = [
            ("Confirmed Decisions", self.decisions),
            ("Proposals & Ideas", self.proposals),
            ("Action Items", self.action_items),
            ("Open Questions", self.open_questions),
            ("Risks & Blockers", self.risks_blockers),
            ("Key Facts & Constraints", self.key_facts),
            ("Topics Discussed", self.topics),
        ]
        word_count = len(self.overview.split())
        for title, items in sections:
            if not items:
                continue
            sec_lines = [f"{title}:"]
            for item in items:
                line = item.format_line()
                line_words = len(line.split())
                if word_count + line_words > max_words and lines:
                    break
                sec_lines.append(line)
                word_count += line_words
            if len(sec_lines) > 1:
                lines.append("\n".join(sec_lines))
            if word_count >= max_words:
                break
        return "\n\n".join(lines).strip()

    def to_dict(self) -> dict[str, Any]:
        """Convert memory to serializable dictionary."""
        def serialize_items(items: list[MemoryItem]) -> list[dict[str, Any]]:
            return [{
                "text": it.text,
                "source_ids": it.source_ids,
                "status": it.status,
                "owner": it.owner,
                "deadline": it.deadline,
            } for it in items]

        return {
            "overview": self.overview,
            "topics": serialize_items(self.topics),
            "decisions": serialize_items(self.decisions),
            "proposals": serialize_items(self.proposals),
            "action_items": serialize_items(self.action_items),
            "open_questions": serialize_items(self.open_questions),
            "risks_blockers": serialize_items(self.risks_blockers),
            "key_facts": serialize_items(self.key_facts),
            "last_compacted_id": self.last_compacted_id,
            "compaction_version": self.compaction_version,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], last_id: int = 0, version: int = 0) -> MeetingMemory:
        """Deserialize structured dict into MeetingMemory object."""
        def parse_items(raw_list: Any) -> list[MemoryItem]:
            if not isinstance(raw_list, list):
                return []
            items: list[MemoryItem] = []
            for entry in raw_list:
                if isinstance(entry, dict) and "text" in entry:
                    raw_src = entry.get("source_ids", [])
                    src_ids = [int(x) for x in raw_src if str(x).isdigit()] if isinstance(raw_src, list) else []
                    items.append(MemoryItem(
                        text=str(entry["text"]).strip(),
                        source_ids=src_ids,
                        status=str(entry.get("status", "confirmed")).strip(),
                        owner=str(entry.get("owner", "")).strip(),
                        deadline=str(entry.get("deadline", "")).strip(),
                    ))
                elif isinstance(entry, str) and entry.strip():
                    items.append(MemoryItem(text=entry.strip()))
            return items

        return cls(
            overview=str(data.get("overview", "")).strip(),
            topics=parse_items(data.get("topics", [])),
            decisions=parse_items(data.get("decisions", [])),
            proposals=parse_items(data.get("proposals", [])),
            action_items=parse_items(data.get("action_items", [])),
            open_questions=parse_items(data.get("open_questions", [])),
            risks_blockers=parse_items(data.get("risks_blockers", [])),
            key_facts=parse_items(data.get("key_facts", [])),
            last_compacted_id=last_id or int(data.get("last_compacted_id", 0)),
            compaction_version=version or int(data.get("compaction_version", 0)),
            updated_at=time.time(),
        )
