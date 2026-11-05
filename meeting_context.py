"""Backward-compatible wrapper for MeetingContextStore."""

from __future__ import annotations

from mac_live_translator.meeting.context import MeetingContextStore
from mac_live_translator.meeting.models import DetectedQuestion, TranscriptEntry

__all__ = ["DetectedQuestion", "MeetingContextStore", "TranscriptEntry"]
