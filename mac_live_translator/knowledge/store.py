"""In-memory SQLite FTS5 index for documentation retrieval."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from mac_live_translator.knowledge.chunker import chunk_document
from mac_live_translator.knowledge.loader import SUPPORTED_EXTENSIONS, collect_folder_files
from mac_live_translator.knowledge.models import DocumentChunk
from mac_live_translator.knowledge.search import clean_fts_token, execute_fts_search

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024
MAX_TOTAL_CHUNKS = 2000


class KnowledgeStore:
    """In-memory SQLite FTS5 search index for local documentation."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._db: sqlite3.Connection | None = None
        self._chunks: dict[str, DocumentChunk] = {}
        self._loaded_paths: dict[str, str] = {}  # norm_path -> display_name
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
            self._loaded_paths.clear()
            self._chunk_counter = 0

    def clear(self) -> None:
        """Reset the knowledge index."""
        self._init_db()

    def get_loaded_files(self) -> list[str]:
        """Return list of loaded filenames."""
        with self._lock:
            return sorted(self._loaded_paths.values())

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

        with self._lock:
            if root.is_dir():
                root_str = str(root)
                stale_paths = [
                    p for p in self._loaded_paths
                    if p.startswith(root_str) and Path(p) not in target_files
                ]
                for p in stale_paths:
                    self._remove_file_locked(p)

        total_added = 0
        for f in target_files:
            total_added += self._index_file(f)
        return total_added

    def _remove_file_locked(self, norm_path: str) -> None:
        """Remove all chunks associated with a canonical file path."""
        cids = [cid for cid, c in self._chunks.items() if c.filepath == norm_path]
        for cid in cids:
            del self._chunks[cid]
            if self._db:
                self._db.execute("DELETE FROM chunks WHERE chunk_id = ?", (cid,))
        self._loaded_paths.pop(norm_path, None)

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
            self._remove_file_locked(norm_path)

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
                self._loaded_paths[norm_path] = filename
            self._db.commit()

        return added_count

    def search(self, query: str, top_k: int = 4) -> list[DocumentChunk]:
        """Deterministic keyword search over documentation chunks."""
        with self._lock:
            if not self._db or not self._chunks:
                return []
            return execute_fts_search(self._db, self._chunks, query, top_k=top_k)

    @staticmethod
    def format_for_prompt(chunks: list[DocumentChunk]) -> str:
        """Format retrieved documentation chunks into a prompt-safe excerpt string."""
        if not chunks:
            return "No relevant documentation found."
        formatted = []
        for c in chunks:
            formatted.append(f"[{c.chunk_id} - {c.heading}]\n{c.text}\n")
        return "\n".join(formatted).strip()
