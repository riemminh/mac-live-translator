"""Keyword extraction, stopword filtering, and prompt formatting for meeting transcripts."""

from __future__ import annotations

import re
from mac_live_translator.meeting.models import TranscriptEntry

STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can't", "cannot", "could", "couldn't",
    "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during",
    "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't",
    "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here",
    "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i",
    "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's",
    "its", "itself", "let's", "me", "more", "most", "mustn't", "my", "myself",
    "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought",
    "our", "ours", "ourselves", "out", "over", "own", "same", "shan't", "she",
    "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such",
    "than", "that", "that's", "the", "their", "theirs", "them", "themselves",
    "then", "there", "there's", "these", "they", "they'd", "they'll", "they're",
    "they've", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were",
    "weren't", "what", "what's", "when", "when's", "where", "where's", "which",
    "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would",
    "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours",
    "yourself", "yourselves",
}


def tokenize_query(query: str) -> set[str]:
    """Extract informative lowercase keywords from query string."""
    words = re.findall(r"\b[A-Za-z0-9_+#.-]+\b", query.casefold())
    return {w for w in words if len(w) > 1 and w not in STOPWORDS}


def format_transcript_for_prompt(
    entries: list[TranscriptEntry],
    unconfirmed_text: str = "",
) -> str:
    """Format transcript entries into a clean prompt text with exact source citations."""
    lines = []
    for e in entries:
        filler_tag = " (filler)" if e.is_filler else ""
        lines.append(f"[T#{e.id}]{filler_tag}: {e.text}")
    if unconfirmed_text.strip():
        lines.append(f"[T#LIVE-UNCONFIRMED]: {unconfirmed_text.strip()}")
    return "\n".join(lines)

