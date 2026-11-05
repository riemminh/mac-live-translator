"""Execution and JSON parsing for incremental Claude Haiku meeting compaction."""

from __future__ import annotations

import json
import re
import threading
from typing import TYPE_CHECKING

from mac_live_translator.copilot.compaction_prompt import (
    COMPACTION_SYSTEM_PROMPT,
    build_compaction_user_prompt,
)
from mac_live_translator.meeting.context import MeetingContextStore
from mac_live_translator.meeting.memory_models import MeetingMemory
from mac_live_translator.meeting.models import TranscriptEntry

if TYPE_CHECKING:
    from mac_live_translator.copilot.client import ClaudeClient, ClaudeUsage


class CompactionError(Exception):
    """Exception raised when Claude compaction fails or returns invalid structured output."""
    pass


def extract_json_payload(raw_text: str) -> str:
    """Extract a valid JSON string from model response, stripping markdown code fences."""
    text = raw_text.strip()
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()
    bracket_match = re.search(r"\{[\s\S]*\}", text)
    if bracket_match:
        return bracket_match.group(0).strip()
    return text


def build_compaction_payload(
    previous_memory: MeetingMemory,
    batch: list[TranscriptEntry],
) -> tuple[str, str]:
    """Generate system and user prompts for Claude Haiku compaction."""
    prev_str = previous_memory.format_for_prompt(max_words=500) if not previous_memory.is_empty() else ""
    batch_str = MeetingContextStore.format_for_prompt(batch)
    user_prompt = build_compaction_user_prompt(prev_str, batch_str)
    return COMPACTION_SYSTEM_PROMPT, user_prompt


def execute_claude_compaction(
    client: ClaudeClient,
    previous_memory: MeetingMemory,
    batch: list[TranscriptEntry],
    stop_event: threading.Event | None = None,
) -> tuple[MeetingMemory, ClaudeUsage]:
    """Stream compaction through Claude Haiku, parse structured JSON, and construct updated memory."""
    if not batch:
        raise CompactionError("Cannot compact an empty transcript batch.")

    system_prompt, user_prompt = build_compaction_payload(previous_memory, batch)
    raw_response, usage = client.stream_chat(
        system_prompt=system_prompt,
        user_message=user_prompt,
        on_text=lambda _: None,
        stop_event=stop_event,
    )

    if stop_event and stop_event.is_set():
        raise CompactionError("Compaction was canceled by the user.")

    cleaned_json = extract_json_payload(raw_response)
    try:
        data = json.loads(cleaned_json)
    except Exception as exc:
        raise CompactionError(f"Failed to parse model JSON: {exc}. Raw: {raw_response[:120]}…") from exc

    if not isinstance(data, dict):
        raise CompactionError(f"Expected JSON object from model, received: {type(data).__name__}")

    max_batch_id = max(e.id for e in batch)
    next_version = previous_memory.compaction_version + 1
    updated_memory = MeetingMemory.from_dict(data, last_id=max_batch_id, version=next_version)

    return updated_memory, usage

