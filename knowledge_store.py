"""Backward-compatible wrapper for KnowledgeStore."""

from __future__ import annotations

from mac_live_translator.knowledge.models import DocumentChunk
from mac_live_translator.knowledge.store import KnowledgeStore

__all__ = ["DocumentChunk", "KnowledgeStore"]
