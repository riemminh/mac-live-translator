"""In-memory SQLite FTS5 index for documentation retrieval."""

from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path

from mac_live_translator.knowledge.chunker import chunk_document
from mac_live_translator.knowledge.loader import SUPPORTED_EXTENSIONS, collect_folder_files
from mac_live_translator.knowledge.models import DocumentChunk

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
        root = Path(path).expanduser().resolve()
        if not root.exists():
            return 0

        target_files: list[Path] = []
        if root.is_file():
            if root.suffix.lower() in SUPPORTED_EXTENSIONS:
                target_files.append(root)
        elif root.is_dir():
            target_files = collect_folder_files(root)

        total_added = 0
        for f in target_files:
            total_added += self._index_file(f)

        return total_added

    def _index_file(self, filepath: Path) -> int:
        """Safely read, chunk, and index/reindex a single file into FTS5 with stable replacement."""
        try:
            if filepath.stat().st_size > MAX_FILE_SIZE_BYTES:
                return 0
            text = filepath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return 0

        filename = filepath.name
        raw_chunks = chunk_document(text, filename)
        if not raw_chunks:
            return 0

        norm_path = str(filepath.resolve())

        with self._lock:
            if self._db is None:
                return 0

            existing_cids = [cid for cid, chunk in self._chunks.items() if chunk.filepath == norm_path]
            for cid in existing_cids:
                del self._chunks[cid]
                self._db.execute("DELETE FROM chunks WHERE chunk_id = ?", (cid,))

            added_count = 0
            for heading, chunk_text in raw_chunks:
                if len(self._chunks) >= MAX_TOTAL_CHUNKS:
                    break
                self._chunk_counter += 1
                cid = f"DOC#{self._chunk_counter}"
                chunk = DocumentChunk(
                    chunk_id=cid,
                    filename=filename,
                    filepath=norm_path,
                    heading=heading,
                    text=chunk_text,
                )
                self._chunks[cid] = chunk
                self._db.execute(
                    "INSERT INTO chunks(chunk_id, filename, heading, content) VALUES (?, ?, ?, ?)",
                    (chunk.chunk_id, chunk.filename, chunk.heading, chunk.text),
                )
                added_count += 1

            if added_count > 0:
                self._loaded_files.add(filename)
            elif filename in self._loaded_files and not any(c.filename == filename for c in self._chunks.values()):
                self._loaded_files.discard(filename)

            self._db.commit()

        return added_count

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

