"""Split Markdown and plain text documents into heading-bound semantic chunks."""

from __future__ import annotations

import re


def chunk_document(content: str, filename: str) -> list[tuple[str, str]]:
    """Split text by Markdown headings and natural paragraph boundaries into (heading, text) pairs."""
    lines = content.splitlines()
    chunks: list[tuple[str, str]] = []
    current_heading = filename
    buffer: list[str] = []
    word_count = 0

    def flush_chunk() -> None:
        nonlocal word_count
        if buffer:
            chunk_text = "\n".join(buffer).strip()
            if chunk_text:
                chunks.append((current_heading, chunk_text))
            buffer.clear()
            word_count = 0

    for line in lines:
        heading_match = re.match(r"^(#{1,4})\s+(.+)$", line.strip())
        if heading_match:
            flush_chunk()
            current_heading = f"{filename} > {heading_match.group(2).strip()}"
            buffer.append(line)
            word_count += len(line.split())
            continue

        if not line.strip():
            if word_count >= 120:
                flush_chunk()
            continue

        buffer.append(line)
        word_count += len(line.split())
        if word_count >= 250:
            flush_chunk()

    flush_chunk()
    return chunks

