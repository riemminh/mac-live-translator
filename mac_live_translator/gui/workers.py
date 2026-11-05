"""Background QThread workers for non-blocking Claude streaming and document indexing."""

from __future__ import annotations

import threading
from PySide6.QtCore import QThread, Signal

from mac_live_translator.context_service.engine import ContextEngine
from mac_live_translator.copilot.assistant import MeetingAssistant
from mac_live_translator.copilot.client import ClaudeClient, ClaudeUsage
from mac_live_translator.copilot.compactor import execute_claude_compaction
from mac_live_translator.copilot.models import CopilotResult, PreparedCopilotRequest
from mac_live_translator.knowledge.store import KnowledgeStore
from mac_live_translator.meeting.context import MeetingContextStore
from mac_live_translator.meeting.memory_store import CompactedMemoryStore


class CopilotWorker(QThread):
    """Background worker executing Claude requests without blocking the Qt GUI thread."""
    chunk_received = Signal(str)
    finished_success = Signal(object)  # CopilotResult
    failed_error = Signal(str)

    def __init__(
        self,
        assistant: MeetingAssistant,
        action_type: str = "help_me_reply",
        user_query: str | None = None,
        unconfirmed_live: str = "",
        prepared_request: PreparedCopilotRequest | None = None,
    ) -> None:
        super().__init__()
        self.assistant = assistant
        self.action_type = action_type
        self.user_query = user_query
        self.unconfirmed_live = unconfirmed_live
        self.prepared_request = prepared_request
        self.stop_event = threading.Event()

    def cancel(self) -> None:
        """Signal background streaming to terminate promptly."""
        self.stop_event.set()

    def run(self) -> None:
        """Run request in background thread and emit Qt signals."""
        try:
            if self.prepared_request is not None:
                result = self.assistant.execute_prepared_request(
                    prepared=self.prepared_request,
                    on_text=lambda token: self.chunk_received.emit(token),
                    stop_event=self.stop_event,
                )
            else:
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


class CompactionWorker(QThread):
    """Background worker executing incremental meeting compaction via Claude."""
    compaction_done = Signal(object, object)  # (MeetingMemory, ClaudeUsage)
    compaction_failed = Signal(str)

    def __init__(
        self,
        client: ClaudeClient,
        memory_store: CompactedMemoryStore,
        context_store: MeetingContextStore,
        min_batch: int = 15,
        force: bool = False,
    ) -> None:
        super().__init__()
        self.client = client
        self.memory_store = memory_store
        self.context_store = context_store
        self.min_batch = min_batch
        self.force = force
        self.stop_event = threading.Event()

    def cancel(self) -> None:
        """Signal compaction to abort."""
        self.stop_event.set()
        self.memory_store.cancel_in_progress()

    def run(self) -> None:
        """Execute compaction workflow safely off the main Qt thread."""
        snapshot = self.memory_store.prepare_compaction_snapshot(
            self.context_store, min_batch=self.min_batch, force=self.force
        )
        if snapshot is None:
            self.compaction_failed.emit("Không có đoạn hội thoại đủ điều kiện để thu gọn.")
            return

        session_id, prev_mem, batch = snapshot
        try:
            updated_mem, usage = execute_claude_compaction(
                client=self.client,
                previous_memory=prev_mem,
                batch=batch,
                stop_event=self.stop_event,
            )
            if self.stop_event.is_set():
                self.memory_store.cancel_in_progress()
                return

            max_batch_id = max(e.id for e in batch)
            committed = self.memory_store.commit_compaction(session_id, updated_mem, max_batch_id)
            if not committed:
                self.compaction_failed.emit("Phiên họp đã thay đổi hoặc được thiết lập lại. Bỏ qua kết quả.")
                return

            self.compaction_done.emit(updated_mem, usage)
        except Exception as exc:
            self.memory_store.cancel_in_progress()
            if not self.stop_event.is_set():
                self.compaction_failed.emit(str(exc))


class UnderstandingAnalysisWorker(QThread):
    """Background worker executing single-pass Claude understanding analysis."""
    analysis_done = Signal(object)
    analysis_failed = Signal(str)

    def __init__(
        self,
        engine: ContextEngine,
        session_id: str = "default",
        force: bool = False,
    ) -> None:
        super().__init__()
        self.engine = engine
        self.session_id = session_id
        self.force = force
        self.stop_event = threading.Event()

    def cancel(self) -> None:
        self.stop_event.set()

    def run(self) -> None:
        try:
            result = self.engine.trigger_analysis(
                session_id=self.session_id,
                force=self.force,
                stop_event=self.stop_event,
            )
            if not self.stop_event.is_set() and result is not None:
                self.analysis_done.emit(result)
        except Exception as exc:
            if not self.stop_event.is_set():
                self.analysis_failed.emit(str(exc))
