"""Parse structured sections and match bracketed citation IDs against retrieved sources."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mac_live_translator.copilot.models import CopilotResult


def extract_citations(text: str) -> list[str]:
    """Find all [T#id] and [DOC#id] citation tokens in text."""
    return re.findall(r"\[(T#\d+|DOC#\d+)\]", text)


def parse_copilot_response(raw_text: str) -> tuple[str, str, list[str], list[str]]:
    """Parse streamed text into English answer, Vietnamese meaning, evidence, and warnings."""
    english = ""
    vietnamese = ""
    evidence: list[str] = []
    warnings: list[str] = []

    sections = re.split(r"(?:\r?\n|^)#{1,4}\s+", raw_text)
    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue
        lines = sec.splitlines()
        header = lines[0].strip().casefold()
        body = "\n".join(lines[1:]).strip()

        if "english" in header:
            english = body
        elif "nghĩa" in header or "vietnamese" in header:
            vietnamese = body
        elif "evidence" in header:
            evidence = [ln.strip("- *") for ln in body.splitlines() if ln.strip("- *")]
        elif "warning" in header or "caveat" in header:
            warnings = [ln.strip("- *") for ln in body.splitlines() if ln.strip("- *") and "none" not in ln.casefold()]

    if not english and raw_text:
        parts = raw_text.split("\n\n", 1)
        english = parts[0].strip()
        if len(parts) > 1:
            vietnamese = parts[1].strip()

    return english, vietnamese, evidence, warnings


def match_citations(
    cited_ids: list[str],
    valid_segments: dict[str, str],
    valid_docs: dict[str, str],
) -> tuple[list[str], list[str]]:
    """Match cited tokens against retrieved segments and document excerpts."""
    matched: list[str] = []
    unverified: list[str] = []

    for cid in cited_ids:
        if cid in valid_segments:
            matched.append(f"[{cid}] (Biên bản: \"{valid_segments[cid]}\")")
        elif cid in valid_docs:
            matched.append(f"[{cid}] (Tài liệu: {valid_docs[cid]})")
        else:
            unverified.append(f"[{cid}]")

    return matched, unverified


def format_evidence_text(result: CopilotResult) -> str:
    """Format matched citations and caveats into human-readable text."""
    ev_lines: list[str] = []
    if result.evidence_citations:
        ev_lines.append("Trích dẫn khớp nguồn trích đoạn:")
        ev_lines.extend(f" • {c}" for c in result.evidence_citations)
    if result.unverified_citations:
        ev_lines.append("\nCảnh báo trích dẫn không có trong nguồn:")
        ev_lines.extend(f" ⚠️ {c}" for c in result.unverified_citations)
    if result.warnings:
        ev_lines.append("\nLưu ý & Điểm chưa rõ:")
        ev_lines.extend(f" ℹ️ {w}" for w in result.warnings)
    return "\n".join(ev_lines) if ev_lines else "Không có trích dẫn bổ sung."
