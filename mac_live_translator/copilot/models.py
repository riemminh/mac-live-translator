"""Data models for Copilot request snapshots and structured execution results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mac_live_translator.copilot.client import ClaudeUsage
from mac_live_translator.knowledge.models import DocumentChunk
from mac_live_translator.meeting.models import DetectedQuestion, TranscriptEntry

if TYPE_CHECKING:
    from mac_live_translator.meeting.memory_models import MeetingMemory


@dataclass(frozen=True)
class PreparedCopilotRequest:
    """Immutable snapshot of retrieved context and exact prompt prepared for Claude."""
    action_type: str
    effective_query: str
    detected_question: DetectedQuestion | None
    recent_segments: list[TranscriptEntry]
    older_segments: list[TranscriptEntry]
    all_segments: list[TranscriptEntry]
    retrieved_docs: list[DocumentChunk]
    unconfirmed_live: str
    system_prompt: str
    user_prompt: str
    compacted_memory: MeetingMemory | None = None
    context_prep_duration: float = 0.0
    created_at: float = 0.0


@dataclass
class CopilotResult:
    """Structured result returned by the Meeting Assistant."""
    action_type: str
    english_answer: str
    vietnamese_meaning: str
    evidence_citations: list[str] = field(default_factory=list)
    unverified_citations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw_response: str = ""
    usage: ClaudeUsage = field(default_factory=ClaudeUsage)
    retrieved_segments: list[TranscriptEntry] = field(default_factory=list)
    retrieved_docs: list[DocumentChunk] = field(default_factory=list)
    prepared_request: PreparedCopilotRequest | None = None
