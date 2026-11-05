"""FTS5 query construction and deterministic document chunk ranking."""

from __future__ import annotations

import re
import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mac_live_translator.knowledge.models import DocumentChunk

FTS_STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "as", "at", "be", "because", "been", "before", "being", "below",
    "between", "both", "but", "by", "can", "could", "did", "do", "does", "doing",
    "down", "during", "each", "few", "for", "from", "further", "had", "has", "have",
    "having", "he", "her", "here", "hers", "herself", "him", "himself", "his",
    "how", "i", "if", "in", "into", "is", "it", "its", "itself", "just", "me",
    "more", "most", "my", "myself", "no", "nor", "not", "of", "off", "on", "once",
    "only", "or", "other", "our", "ours", "ourselves", "out", "over", "own", "say",
    "same", "she", "should", "so", "some", "such", "than", "that", "the", "their",
    "theirs", "them", "themselves", "then", "there", "these", "they", "this",
    "those", "through", "to", "too", "under", "until", "up", "very", "was", "we",
    "were", "what", "when", "where", "which", "while", "who", "whom", "why",
    "will", "with", "would", "you", "your", "yours", "yourself", "yourselves",
}


def clean_fts_token(word: str) -> str:
    """Sanitize alphanumeric search token for SQLite FTS5 matching."""
    return re.sub(r"[^\w]", "", word).strip()


def extract_search_terms(query: str) -> list[str]:
    """Extract informative, ordered keywords from query ignoring filler words."""
    raw_tokens = re.findall(r"\b[A-Za-z0-9_+#.-]+\b", query)
    cleaned = [clean_fts_token(t) for t in raw_tokens]
    seen: set[str] = set()
    terms: list[str] = []
    for t in cleaned:
        tl = t.casefold()
        if len(tl) > 1 and tl not in FTS_STOPWORDS and tl not in seen:
            seen.add(tl)
            terms.append(t)
    return terms


def execute_fts_search(
    db: sqlite3.Connection,
    chunks: dict[str, DocumentChunk],
    query: str,
    top_k: int = 4,
) -> list[DocumentChunk]:
    """Execute high-precision FTS5 search (AND first, fallback to BM25-ranked OR)."""
    terms = extract_search_terms(query)
    if not terms or not chunks:
        return []

    collected_cids: list[str] = []

    # Stage 1: High-precision AND query if multiple terms exist
    if len(terms) >= 2:
        and_expr = " AND ".join(f'"{t}"' for t in terms[:6])
        try:
            cursor = db.execute(
                "SELECT chunk_id, bm25(chunks) AS score FROM chunks WHERE chunks MATCH ? ORDER BY score LIMIT ?",
                (and_expr, top_k),
            )
            for row in cursor.fetchall():
                if row[0] in chunks and row[0] not in collected_cids:
                    collected_cids.append(row[0])
        except sqlite3.OperationalError:
            pass

    # Stage 2: Ranked OR query if AND query didn't fill top_k
    if len(collected_cids) < top_k:
        needed = top_k - len(collected_cids)
        or_expr = " OR ".join(f'"{t}"' for t in terms[:8])
        try:
            cursor = db.execute(
                "SELECT chunk_id, bm25(chunks) AS score FROM chunks WHERE chunks MATCH ? ORDER BY score LIMIT ?",
                (or_expr, top_k * 2),
            )
            for row in cursor.fetchall():
                if row[0] in chunks and row[0] not in collected_cids:
                    collected_cids.append(row[0])
                    if len(collected_cids) >= top_k:
                        break
        except sqlite3.OperationalError:
            pass

    if collected_cids:
        return [chunks[cid] for cid in collected_cids]

    # Stage 3: Deterministic in-memory substring fallback
    scores: list[tuple[float, DocumentChunk]] = []
    for chunk in chunks.values():
        score = 0.0
        content_lower = chunk.text.casefold()
        heading_lower = chunk.heading.casefold()
        for term in terms:
            tl = term.casefold()
            if tl in heading_lower:
                score += 3.0
            if tl in content_lower:
                score += 1.0
        if score > 0.0:
            scores.append((score, chunk))

    scores.sort(key=lambda x: x[0], reverse=True)
    return [chunk for _, chunk in scores[:top_k]]

