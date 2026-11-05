"""Backward-compatible wrapper for ClaudeClient."""

from __future__ import annotations

from mac_live_translator.copilot.client import ClaudeClient, ClaudeClientError, ClaudeUsage

__all__ = ["ClaudeClient", "ClaudeClientError", "ClaudeUsage"]
