"""Backward-compatible wrapper for MeetingContextStore."""

from __future__ import annotations

from mac_live_translator.meeting.context import MeetingContextStore
from mac_live_translator.meeting.models import TranscriptEntry

__all__ = ["MeetingContextStore", "TranscriptEntry"]
