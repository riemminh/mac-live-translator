"""Local in-memory document store using SQLite FTS5 for documentation retrieval."""

from __future__ import annotations

import re
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DocumentChunk:
    """An immutable retrieved chunk from user-provided Markdown or TXT documentation."""
    chunk_id: str
    filename: str
    filepath: str
    heading: str
    text: str


MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB safety limit per file
MAX_TOTAL_CHUNKS = 2000


def clean_fts_token(word: str) -> str:
    """Remove special characters for FTS5 boolean matching."""
    return re.sub(r"[^\w]", "", word).strip()


class KnowledgeStore:
    """In-memory SQLite FTS5 search index for local documentation."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._db: sqlite3.Connection | None = None
        self._chunks: dict[str, DocumentChunk] = {}
        self._loaded_files: set[str] = set()
        self._chunk_counter = 0
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            if self._db is not None:
                try:
                    self._db.close()
                except Exception:
                    pass
            # In-memory database with FTS5 table
            self._db = sqlite3.connect(":memory:", check_same_thread=False)
            self._db.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(
                    chunk_id UNINDEXED,
                    filename,
                    heading,
                    content,
                    tokenize='porter unicode61'
                )
                """
            )
            self._chunks.clear()
            self._loaded_files.clear()
            self._chunk_counter = 0

    def clear(self) -> None:
        """Reset the knowledge index."""
        self._init_db()

    def get_loaded_files(self) -> list[str]:
        """Return list of loaded filenames."""
        with self._lock:
            return sorted(self._loaded_files)

    def get_chunk_count(self) -> int:
        """Return total number of indexed document chunks."""
        with self._lock:
            return len(self._chunks)

    def load_path(self, path: Path | str) -> int:
        """Load and index a file or folder of .md and .txt files."""
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return 0

        target_files: list[Path] = []
        if p.is_file():
            if p.suffix.lower() in {".md", ".markdown", ".txt"}:
                target_files.append(p)
        elif p.is_dir():
            # Scan only the selected directory (and immediate subdirectories)
            for item in p.rglob("*"):
                if item.is_file() and item.suffix.lower() in {".md", ".markdown", ".txt"}:
                    target_files.append(item)

        total_added = 0
        for f in target_files:
            total_added += self._index_file(f)

        return total_added

    def _index_file(self, filepath: Path) -> int:
        """Safely read and chunk a single text or Markdown file into FTS5."""
        try:
            if filepath.stat().st_size > MAX_FILE_SIZE_BYTES:
                return 0
            text = filepath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return 0

        filename = filepath.name
        chunks = self._chunk_document(text, filename, str(filepath))
        if not chunks:
            return 0

        with self._lock:
            if self._db is None:
                return 0
            self._loaded_files.add(filename)
            for chunk in chunks:
                if len(self._chunks) >= MAX_TOTAL_CHUNKS:
                    break
                self._chunks[chunk.chunk_id] = chunk
                self._db.execute(
                    "INSERT INTO chunks(chunk_id, filename, heading, content) VALUES (?, ?, ?, ?)",
                    (chunk.chunk_id, chunk.filename, chunk.heading, chunk.text),
                )
            self._db.commit()

        return len(chunks)

    def _chunk_document(self, content: str, filename: str, filepath: str) -> list[DocumentChunk]:
        """Split text by Markdown headings and natural paragraph boundaries."""
        lines = content.splitlines()
        chunks: list[DocumentChunk] = []
        current_heading = filename
        buffer: list[str] = []
        word_count = 0

        def flush_chunk():
            nonlocal word_count
            if buffer:
                chunk_text = "\n".join(buffer).strip()
                if chunk_text:
                    self._chunk_counter += 1
                    cid = f"DOC#{self._chunk_counter}"
                    chunks.append(
                        DocumentChunk(
                            chunk_id=cid,
                            filename=filename,
                            filepath=filepath,
                            heading=current_heading,
                            text=chunk_text,
                        )
                    )
                buffer.clear()
                word_count = 0

        for line in lines:
            heading_match = re.match(r"^(#{1,4})\s+(.+)$", line.strip())
            if heading_match:
                # Flush previous paragraph before starting new heading section
                flush_chunk()
                current_heading = f"{filename} > {heading_match.group(2).strip()}"
                buffer.append(line)
                word_count += len(line.split())
                continue

            if not line.strip():
                # Paragraph break
                if word_count >= 120:
                    flush_chunk()
                continue

            buffer.append(line)
            word_count += len(line.split())
            if word_count >= 250:
                flush_chunk()

        flush_chunk()
        return chunks

    def search(self, query: str, top_k: int = 4) -> list[DocumentChunk]:
        """Deterministic keyword search over documentation chunks."""
        words = [clean_fts_token(w) for w in query.split()]
        words = [w for w in words if len(w) > 1 and w.casefold() not in {
            "the", "and", "for", "with", "that", "this", "what", "how", "when", "about"
        }]

        if not words:
            return []

        with self._lock:
            if not self._db or not self._chunks:
                return []

            # Match any word using FTS OR logic
            match_expr = " OR ".join(f'"{w}"' for w in words[:8])
            try:
                cursor = self._db.execute(
                    """
                    SELECT chunk_id, rank
                    FROM chunks
                    WHERE chunks MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (match_expr, top_k),
                )
                rows = cursor.fetchall()
                results = [self._chunks[r[0]] for r in rows if r[0] in self._chunks]
                if results:
                    return results
            except sqlite3.OperationalError:
                pass

            # Fallback simple substring scoring if FTS fails
            scores: list[tuple[int, DocumentChunk]] = []
            for chunk in self._chunks.values():
                content_lower = chunk.text.casefold()
                score = sum(1 for w in words if w.casefold() in content_lower)
                if score > 0:
                    scores.append((score, chunk))

            scores.sort(key=lambda x: x[0], reverse=True)
            return [chunk for _, chunk in scores[:top_k]]

    @staticmethod
    def format_for_prompt(chunks: list[DocumentChunk]) -> str:
        """Format retrieved documentation chunks into a prompt-safe excerpt string."""
        if not chunks:
            return "No relevant documentation found."
        formatted = []
        for c in chunks:
            formatted.append(f"[{c.chunk_id} - {c.heading}]\n{c.text}\n")
        return "\n".join(formatted).strip()
