"""Parse structured sections and match bracketed citation IDs against retrieved sources."""

from __future__ import annotations

import re


def extract_citations(text: str) -> list[str]:
    """Find all [T#id] and [DOC#id] citation tokens in text."""
    return re.findall(r"\[(T#\d+|DOC#\d+)\]", text)


def parse_copilot_response(raw_text: str) -> tuple[str, str, list[str], list[str]]:
    """Parse streamed text into English answer, Vietnamese meaning, evidence, and warnings."""
    english = ""
    vietnamese = ""
    evidence: list[str] = []
    warnings: list[str] = []

    sections = re.split(r"###\s+", raw_text)
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

