"""Helper bridging single-pass understanding semantic items into CompactedMemoryStore."""

from __future__ import annotations

from typing import Any

from mac_live_translator.meeting.memory_models import MeetingMemory, MemoryItem
from mac_live_translator.meeting.memory_store import CompactedMemoryStore


def merge_analysis_into_memory(
    memory_store: CompactedMemoryStore,
    decisions: list[dict[str, Any]],
    proposals: list[dict[str, Any]],
    action_items: list[dict[str, Any]],
    open_questions: list[dict[str, Any]],
    key_facts: list[dict[str, Any]],
    overview: str = "",
    batch_ids: list[int] | None = None,
) -> bool:
    """Merge newly analyzed structured items into the CompactedMemoryStore."""
    current_mem = memory_store.get_memory()
    u_dec = [MemoryItem(text=d["text"], source_ids=d.get("source_ids", []), status="confirmed") for d in decisions]
    u_prop = [MemoryItem(text=p["text"], source_ids=p.get("source_ids", []), status="proposed") for p in proposals]
    u_act = [
        MemoryItem(
            text=a["text"],
            source_ids=a.get("source_ids", []),
            owner=a.get("owner", ""),
            deadline=a.get("deadline", ""),
            status=a.get("status", "confirmed"),
        )
        for a in action_items
    ]
    u_q = [MemoryItem(text=q["text"], source_ids=q.get("source_ids", [])) for q in open_questions]
    u_facts = [MemoryItem(text=f["text"], source_ids=f.get("source_ids", [])) for f in key_facts]

    max_bid = max(batch_ids) if batch_ids else 0
    merged_mem = MeetingMemory(
        overview=overview or current_mem.overview,
        topics=current_mem.topics,
        decisions=(u_dec + current_mem.decisions)[:25],
        proposals=(u_prop + current_mem.proposals)[:25],
        action_items=(u_act + current_mem.action_items)[:25],
        open_questions=(u_q + current_mem.open_questions)[:25],
        risks_blockers=current_mem.risks_blockers,
        key_facts=(u_facts + current_mem.key_facts)[:25],
        last_compacted_id=max_bid if max_bid > 0 else current_mem.last_compacted_id,
        compaction_version=current_mem.compaction_version + 1,
    )
    return memory_store.commit_compaction(
        session_id=memory_store.get_session_id(),
        new_memory=merged_mem,
        max_batch_id=max_bid,
    )

