"""Backward-compatible wrapper for MeetingAssistant."""

from __future__ import annotations

from mac_live_translator.copilot.assistant import MeetingAssistant
from mac_live_translator.copilot.models import CopilotResult, PreparedCopilotRequest

__all__ = ["CopilotResult", "MeetingAssistant", "PreparedCopilotRequest"]
