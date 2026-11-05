"""Background QThread workers for non-blocking Claude streaming and document indexing."""

from __future__ import annotations

import threading
from PySide6.QtCore import QThread, Signal

from mac_live_translator.copilot.assistant import CopilotResult, MeetingAssistant
from mac_live_translator.knowledge.store import KnowledgeStore


class CopilotWorker(QThread):
    """Background worker executing Claude requests without blocking the Qt GUI thread."""
    chunk_received = Signal(str)
    finished_success = Signal(object)  # CopilotResult
    failed_error = Signal(str)

    def __init__(
        self,
        assistant: MeetingAssistant,
        action_type: str,
        user_query: str | None,
        unconfirmed_live: str,
    ) -> None:
        super().__init__()
        self.assistant = assistant
        self.action_type = action_type
        self.user_query = user_query
        self.unconfirmed_live = unconfirmed_live
        self.stop_event = threading.Event()

    def cancel(self) -> None:
        """Signal background streaming to terminate promptly."""
        self.stop_event.set()

    def run(self) -> None:
        """Run request in background thread and emit Qt signals."""
        try:
            result = self.assistant.process_request(
                action_type=self.action_type,
                user_query=self.user_query,
                unconfirmed_live_text=self.unconfirmed_live,
                on_text=lambda token: self.chunk_received.emit(token),
                stop_event=self.stop_event,
            )
            if not self.stop_event.is_set():
                self.finished_success.emit(result)
        except Exception as exc:
            if not self.stop_event.is_set():
                self.failed_error.emit(str(exc))


class KnowledgeIndexWorker(QThread):
    """Background worker indexing documentation files without freezing the UI."""
    indexing_done = Signal(int, str)
    indexing_failed = Signal(str)

    def __init__(self, knowledge_store: KnowledgeStore, path: str) -> None:
        super().__init__()
        self.knowledge_store = knowledge_store
        self.path = path

    def run(self) -> None:
        """Index target file or folder in background thread."""
        try:
            added = self.knowledge_store.load_path(self.path)
            self.indexing_done.emit(added, self.path)
        except Exception as exc:
            self.indexing_failed.emit(str(exc))

