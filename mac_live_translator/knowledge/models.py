"""Documentation chunk data model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentChunk:
    """An immutable retrieved chunk from user-provided Markdown or TXT documentation."""
    chunk_id: str
    filename: str
    filepath: str
    heading: str
    text: str

