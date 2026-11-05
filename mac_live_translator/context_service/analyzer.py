"""Single-pass Claude Haiku analysis execution, JSON parsing, and schema validation."""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from typing import Any

from mac_live_translator.context_service.models import MeaningCard
from mac_live_translator.context_service.prompts import (
    UNDERSTANDING_SYSTEM_PROMPT,
    build_analysis_user_prompt,
)
from mac_live_translator.copilot.client import ClaudeClient, ClaudeUsage


@dataclass
class SinglePassAnalysisResult:
    """Validated structured output from single-pass Claude Haiku analysis."""
    topic: str
    pinned_question: str | None
    meaning_cards: list[MeaningCard]
    decisions: list[dict[str, Any]]
    proposals: list[dict[str, Any]]
    action_items: list[dict[str, Any]]
    open_questions: list[dict[str, Any]]
    memory_overview: str
    usage: ClaudeUsage
    raw_response: str


def clean_json_text(raw_text: str) -> str:
    """Extract valid JSON from raw Claude response, stripping code fences."""
    text = raw_text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    br_match = re.search(r"\{[\s\S]*\}", text)
    if br_match:
        return br_match.group(0).strip()
    return text


def filter_valid_source_ids(raw_ids: Any, valid_set: set[int]) -> list[int]:
    """Ensure cited source IDs actually exist in the session's transcript."""
    if not isinstance(raw_ids, list):
        return []
    res = []
    for x in raw_ids:
        try:
            val = int(x)
            if val in valid_set:
                res.append(val)
        except (ValueError, TypeError):
            continue
    return res


def execute_single_pass_analysis(
    client: ClaudeClient,
    batch_text: str,
    valid_segment_ids: set[int],
    current_topic: str = "",
    memory_summary: str = "",
    older_evidence: str = "",
    starting_card_id: int = 1,
    stop_event: threading.Event | None = None,
) -> SinglePassAnalysisResult:
    """Execute single-pass Claude Haiku analysis and validate output independently."""
    user_prompt = build_analysis_user_prompt(
        batch_text=batch_text,
        current_topic=current_topic,
        memory_summary=memory_summary,
        older_evidence=older_evidence,
    )

    raw_text, usage = client.stream_chat(
        system_prompt=UNDERSTANDING_SYSTEM_PROMPT,
        user_message=user_prompt,
        on_text=lambda _: None,
        stop_event=stop_event,
    )

    if stop_event and stop_event.is_set():
        raise RuntimeError("Claude analysis canceled.")

    cleaned = clean_json_text(raw_text)
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("Model output did not contain a JSON object.")

    topic = str(data.get("topic", "")).strip() or current_topic or "Chủ đề kỹ thuật chung"
    pinned_q = data.get("pinned_question")
    pinned_question = str(pinned_q).strip() if pinned_q and str(pinned_q).strip() else None

    # Parse and validate meaning cards
    cards: list[MeaningCard] = []
    card_id = starting_card_id
    raw_cards = data.get("meaning_cards", [])
    if isinstance(raw_cards, list):
        for rc in raw_cards:
            if not isinstance(rc, dict):
                continue
            hl = str(rc.get("headline", "")).strip()
            if not hl:
                continue
            bullets = [str(b).strip() for b in rc.get("bullet_points", []) if str(b).strip()]
            cat = str(rc.get("category", "key_point")).strip()
            imp = str(rc.get("importance", "normal")).strip()
            src_ids = filter_valid_source_ids(rc.get("source_ids", []), valid_segment_ids)
            cards.append(MeaningCard(
                card_id=card_id,
                headline=hl,
                bullet_points=bullets,
                category=cat,
                source_ids=src_ids,
                importance=imp,
                topic=topic,
            ))
            card_id += 1

    def parse_items(key: str) -> list[dict[str, Any]]:
        raw_list = data.get(key, [])
        if not isinstance(raw_list, list):
            return []
        items = []
        for it in raw_list:
            if not isinstance(it, dict) or not str(it.get("text", "")).strip():
                continue
            srcs = filter_valid_source_ids(it.get("source_ids", []), valid_segment_ids)
            item_dict: dict[str, Any] = {"text": str(it["text"]).strip(), "source_ids": srcs}
            if "owner" in it:
                item_dict["owner"] = str(it.get("owner", "")).strip()
            if "deadline" in it:
                item_dict["deadline"] = str(it.get("deadline", "")).strip()
            if "status" in it:
                item_dict["status"] = str(it.get("status", "confirmed")).strip()
            items.append(item_dict)
        return items

    return SinglePassAnalysisResult(
        topic=topic,
        pinned_question=pinned_question,
        meaning_cards=cards,
        decisions=parse_items("decisions"),
        proposals=parse_items("proposals"),
        action_items=parse_items("action_items"),
        open_questions=parse_items("open_questions"),
        memory_overview=str(data.get("memory_overview", "")).strip(),
        usage=usage,
        raw_response=raw_text,
    )
