"""Desktop GUI providing Live Meeting Follow translation and Claude Meeting Copilot."""

from __future__ import annotations

import os
import queue
import statistics
import sys
import threading
import time
from collections import deque
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
                               QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QMainWindow, QMessageBox, QPushButton,
                               QTabWidget, QTextEdit, QVBoxLayout, QWidget)

import main as engine
import live_pipeline
from claude_client import ClaudeClient, ClaudeClientError
from knowledge_store import KnowledgeStore
from meeting_assistant import MeetingAssistant, CopilotResult
from meeting_context import MeetingContextStore


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
        self.stop_event.set()

    def run(self) -> None:
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
        try:
            added = self.knowledge_store.load_path(self.path)
            self.indexing_done.emit(added, self.path)
        except Exception as exc:
            self.indexing_failed.emit(str(exc))


class Window(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Mac Live Translator & Meeting Copilot")
        self.resize(880, 720)

        # Core Pipeline State
        self.events: queue.Queue[tuple[str, dict]] = queue.Queue(maxsize=512)
        self.event_overflow = threading.Event()
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.final_en: list[str] = []
        self.final_vi: list[str] = []
        self.current_id: int | None = None
        self.final_en_ids: set[int] = set()
        self.final_vi_ids: set[int] = set()
        self.vi_revisions: dict[int, int] = {}
        self.preview_id: int | None = None
        self.first_english: dict[int, float] = {}
        self.first_vietnamese_rendered: dict[int, float] = {}
        self.first_vietnamese_received: dict[int, float] = {}
        self.traces: dict[int, dict[str, float]] = {}
        self.recent_thought_groups: deque[str] = deque(maxlen=2)
        self.results: list[tuple[float, float, float, float]] = []
        self.coverage = {"english_words": 0, "covered_words": 0,
                         "fragments": 0, "revisions": 0, "skipped": 0}

        # Meeting Copilot Subsystems
        self.context_store = MeetingContextStore(max_entries=1500)
        self.knowledge_store = KnowledgeStore()
        self.claude_client = ClaudeClient(api_key=os.environ.get("ANTHROPIC_API_KEY", "").strip())
        self.assistant = MeetingAssistant(self.context_store, self.knowledge_store, self.claude_client)
        self.copilot_worker: CopilotWorker | None = None
        self.knowledge_worker: KnowledgeIndexWorker | None = None

        # Build UI Tabs
        root = QWidget()
        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(6)

        self.tabs = QTabWidget()
        self.translation_tab = self._create_translation_tab()
        self.copilot_tab = self._create_copilot_tab()
        self.tabs.addTab(self.translation_tab, "🎧 Live Translation (Trực tiếp)")
        self.tabs.addTab(self.copilot_tab, "🤖 Meeting Copilot (Trợ lý trả lời)")
        main_layout.addWidget(self.tabs)

        self.setCentralWidget(root)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.drain)
        self.timer.start(50)

    # -------------------------------------------------------------------------
    # Tab 1: Live Translation & Meeting Follow Mode
    # -------------------------------------------------------------------------
    def _create_translation_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # Device selection row
        row = QHBoxLayout()
        self.input = QComboBox()
        self.input.setMinimumWidth(240)
        self.output = QComboBox()
        self.output.setMinimumWidth(240)
        for i, dev in enumerate(engine.devices()):
            if dev["max_input_channels"] and "blackhole 2ch" in dev["name"].casefold():
                self.input.addItem(f"{i}: {dev['name']}", i)
            if dev["max_output_channels"] and not any(x in dev["name"].casefold() for x in ("blackhole", "multi-output", "aggregate", "loopback")):
                self.output.addItem(f"{i}: {dev['name']}", i)
        row.addWidget(QLabel("Capture:"))
        row.addWidget(self.input)
        row.addWidget(QLabel("Headphones:"))
        row.addWidget(self.output)
        layout.addLayout(row)

        self.status = QLabel("Stopped — set macOS Output to a Multi-Output Device containing BlackHole and headphones")
        self.status.setStyleSheet("color: #555; font-size: 11px;")
        layout.addWidget(self.status)

        self.metrics = QLabel("Audio → first EN: —  ·  first VI: —  ·  final VI: —")
        self.metrics.setStyleSheet("color: #333; font-size: 11px; font-weight: 500;")
        layout.addWidget(self.metrics)

        # Meeting Follow Live Focus Container
        focus_box = QFrame()
        focus_box.setFrameShape(QFrame.Shape.StyledPanel)
        focus_box.setStyleSheet(
            "QFrame { background-color: #f8fafc; border: 1px solid #cbd5e1; border-radius: 8px; }"
        )
        focus_layout = QVBoxLayout(focus_box)
        focus_layout.setContentsMargins(12, 8, 12, 10)
        focus_layout.setSpacing(4)

        self.context_label = QLabel("Ngữ cảnh gần nhất: —")
        self.context_label.setWordWrap(True)
        self.context_label.setStyleSheet("color: #64748b; font-size: 11px; font-style: italic;")
        focus_layout.addWidget(self.context_label)

        self.vietnamese_live = QLabel("Chưa có bản dịch trực tiếp")
        self.vietnamese_live.setWordWrap(True)
        self.vietnamese_live.setStyleSheet(
            "color: #0369a1; font-size: 17px; font-weight: 700; min-height: 40px; line-height: 1.3;"
        )
        focus_layout.addWidget(self.vietnamese_live)

        self.english_live = QLabel("Waiting for speech…")
        self.english_live.setWordWrap(True)
        self.english_live.setStyleSheet("color: #334155; font-size: 12px;")
        focus_layout.addWidget(self.english_live)

        layout.addWidget(focus_box)

        # Subtitle history
        layout.addWidget(QLabel("Lịch sử bản dịch tiếng Việt (Vietnamese History)"))
        self.vietnamese = QTextEdit()
        self.vietnamese.setReadOnly(True)
        layout.addWidget(self.vietnamese, 1)

        layout.addWidget(QLabel("Biên bản tiếng Anh gốc (English Transcript)"))
        self.english = QTextEdit()
        self.english.setReadOnly(True)
        layout.addWidget(self.english, 1)

        # Bottom controls
        controls = QHBoxLayout()
        self.start_button = QPushButton("Start Meeting Follow")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.top = QCheckBox("Always on top")
        self.top.toggled.connect(self.toggle_top)
        self.start_button.clicked.connect(self.start)
        self.stop_button.clicked.connect(self.stop)
        controls.addWidget(self.start_button)
        controls.addWidget(self.stop_button)
        controls.addWidget(self.top)
        layout.addLayout(controls)

        return tab

    # -------------------------------------------------------------------------
    # Tab 2: Meeting Copilot & Question Answering
    # -------------------------------------------------------------------------
    def _create_copilot_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        # Card 1: Cloud Privacy & API Authorization
        auth_box = QFrame()
        auth_box.setStyleSheet("QFrame { background-color: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 6px; }")
        auth_layout = QVBoxLayout(auth_box)
        auth_layout.setContentsMargins(10, 6, 10, 6)
        auth_layout.setSpacing(4)

        top_auth_row = QHBoxLayout()
        self.cloud_opt_in = QCheckBox("Cho phép sử dụng Claude AI (Cloud Assistance Opt-In)")
        self.cloud_opt_in.setStyleSheet("font-weight: bold; color: #0f172a;")
        self.cloud_opt_in.setChecked(self.claude_client.is_configured())
        self.cloud_opt_in.toggled.connect(self._on_opt_in_toggled)
        top_auth_row.addWidget(self.cloud_opt_in)

        top_auth_row.addSpacing(15)
        top_auth_row.addWidget(QLabel("Model:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(["claude-haiku-5-5", "claude-3-5-haiku-20241022"])
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        top_auth_row.addWidget(self.model_combo)
        auth_layout.addLayout(top_auth_row)

        key_row = QHBoxLayout()
        key_row.addWidget(QLabel("Anthropic API Key:"))
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("sk-ant-api03-...")
        if self.claude_client.api_key:
            self.api_key_input.setText(self.claude_client.api_key)
        self.api_key_input.textChanged.connect(self._on_api_key_changed)
        key_row.addWidget(self.api_key_input, 1)

        self.btn_toggle_key = QPushButton("Hiện/Ẩn Key")
        self.btn_toggle_key.clicked.connect(self._toggle_key_visibility)
        key_row.addWidget(self.btn_toggle_key)
        auth_layout.addLayout(key_row)

        notice_label = QLabel(
            "Quyền riêng tư: Chỉ trích đoạn hội thoại (~3 phút) và tài liệu liên quan được gửi lên Anthropic API khi bấm nút. Biên bản không lưu vào đĩa."
        )
        notice_label.setStyleSheet("color: #475569; font-size: 11px; font-style: italic;")
        auth_layout.addWidget(notice_label)
        layout.addWidget(auth_box)

        # Card 2: Knowledge Documents & Meeting Context Snapshot
        store_row = QHBoxLayout()

        # Knowledge Store UI
        doc_box = QFrame()
        doc_box.setStyleSheet("QFrame { background-color: #faf5ff; border: 1px solid #e9d5ff; border-radius: 6px; }")
        doc_layout = QVBoxLayout(doc_box)
        doc_layout.setContentsMargins(8, 6, 8, 6)
        self.knowledge_status = QLabel("Tài liệu (.md, .txt): 0 tệp (0 đoạn)")
        self.knowledge_status.setStyleSheet("font-weight: 600; color: #6b21a8; font-size: 11px;")
        doc_layout.addWidget(self.knowledge_status)

        doc_btn_row = QHBoxLayout()
        btn_add_file = QPushButton("+ Thêm tệp")
        btn_add_file.clicked.connect(self._add_knowledge_file)
        btn_add_dir = QPushButton("+ Thêm thư mục")
        btn_add_dir.clicked.connect(self._add_knowledge_folder)
        btn_clear_doc = QPushButton("Xóa")
        btn_clear_doc.clicked.connect(self._clear_knowledge)
        doc_btn_row.addWidget(btn_add_file)
        doc_btn_row.addWidget(btn_add_dir)
        doc_btn_row.addWidget(btn_clear_doc)
        doc_layout.addLayout(doc_btn_row)
        store_row.addWidget(doc_box, 1)

        # Meeting Context UI
        ctx_box = QFrame()
        ctx_box.setStyleSheet("QFrame { background-color: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 6px; }")
        ctx_layout = QVBoxLayout(ctx_box)
        ctx_layout.setContentsMargins(8, 6, 8, 6)
        self.context_status = QLabel("Biên bản cuộc họp: 0 câu (0 từ)")
        self.context_status.setStyleSheet("font-weight: 600; color: #166534; font-size: 11px;")
        ctx_layout.addWidget(self.context_status)

        ctx_btn_row = QHBoxLayout()
        btn_review_ctx = QPushButton("Xem trước ngữ cảnh")
        btn_review_ctx.clicked.connect(self._review_context_snapshot)
        btn_clear_ctx = QPushButton("Xóa biên bản")
        btn_clear_ctx.clicked.connect(self._clear_meeting_context)
        ctx_btn_row.addWidget(btn_review_ctx)
        ctx_btn_row.addWidget(btn_clear_ctx)
        ctx_layout.addLayout(ctx_btn_row)
        store_row.addWidget(ctx_box, 1)

        layout.addLayout(store_row)

        # Card 3: Action & Question Input
        action_box = QFrame()
        action_layout = QVBoxLayout(action_box)
        action_layout.setContentsMargins(4, 2, 4, 2)
        action_layout.setSpacing(4)

        self.question_input = QLineEdit()
        self.question_input.setPlaceholderText("Câu hỏi hoặc yêu cầu cụ thể (để trống để tự động phân tích câu hỏi gần nhất trong cuộc họp)…")
        action_layout.addWidget(self.question_input)

        action_btn_row = QHBoxLayout()
        self.btn_help_reply = QPushButton("💬 Help Me Reply (Gợi ý câu trả lời)")
        self.btn_help_reply.setStyleSheet("font-weight: bold; background-color: #e0f2fe; color: #0369a1; padding: 6px 12px;")
        self.btn_help_reply.clicked.connect(lambda: self._trigger_copilot("help_me_reply"))
        action_btn_row.addWidget(self.btn_help_reply)

        self.btn_explain = QPushButton("🔍 Explain Context (Giải thích cuộc họp)")
        self.btn_explain.clicked.connect(lambda: self._trigger_copilot("explain_context"))
        action_btn_row.addWidget(self.btn_explain)

        self.btn_suggest = QPushButton("❓ Suggest Question (Gợi ý câu hỏi)")
        self.btn_suggest.clicked.connect(lambda: self._trigger_copilot("suggest_question"))
        action_btn_row.addWidget(self.btn_suggest)

        self.btn_cancel_copilot = QPushButton("⏹ Hủy")
        self.btn_cancel_copilot.setEnabled(False)
        self.btn_cancel_copilot.clicked.connect(self._cancel_copilot)
        action_btn_row.addWidget(self.btn_cancel_copilot)

        action_layout.addLayout(action_btn_row)
        layout.addWidget(action_box)

        # Card 4: Streaming English Response (Hero)
        ans_box = QFrame()
        ans_box.setStyleSheet("QFrame { background-color: #f8fafc; border: 1px solid #cbd5e1; border-radius: 8px; }")
        ans_layout = QVBoxLayout(ans_box)
        ans_layout.setContentsMargins(10, 8, 10, 8)
        ans_layout.setSpacing(4)

        ans_top_row = QHBoxLayout()
        ans_top_row.addWidget(QLabel("Suggested Spoken English (1-3 câu để nói ngay):"))
        ans_top_row.addStretch()
        self.btn_copy_english = QPushButton("📋 Copy English")
        self.btn_copy_english.clicked.connect(self._copy_english_answer)
        ans_top_row.addWidget(self.btn_copy_english)
        ans_layout.addLayout(ans_top_row)

        self.english_answer_view = QTextEdit()
        self.english_answer_view.setReadOnly(True)
        self.english_answer_view.setStyleSheet("font-size: 15px; font-weight: bold; color: #0f172a; min-height: 70px;")
        ans_layout.addWidget(self.english_answer_view)

        layout.addWidget(ans_box, 1)

        # Card 5: Vietnamese Meaning & Evidence Citations
        details_row = QHBoxLayout()

        vi_box = QFrame()
        vi_box.setStyleSheet("QFrame { background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; }")
        vi_layout = QVBoxLayout(vi_box)
        vi_layout.setContentsMargins(8, 6, 8, 6)
        vi_layout.addWidget(QLabel("Ý nghĩa tiếng Việt (Vietnamese Meaning):"))
        self.vietnamese_meaning_view = QTextEdit()
        self.vietnamese_meaning_view.setReadOnly(True)
        self.vietnamese_meaning_view.setStyleSheet("color: #334155; font-size: 12px;")
        vi_layout.addWidget(self.vietnamese_meaning_view)
        details_row.addWidget(vi_box, 1)

        ev_box = QFrame()
        ev_box.setStyleSheet("QFrame { background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; }")
        ev_layout = QVBoxLayout(ev_box)
        ev_layout.setContentsMargins(8, 6, 8, 6)
        ev_layout.addWidget(QLabel("Dẫn chứng xác thực (Verified Evidence):"))
        self.evidence_view = QTextEdit()
        self.evidence_view.setReadOnly(True)
        self.evidence_view.setStyleSheet("color: #475569; font-size: 11px;")
        ev_layout.addWidget(self.evidence_view)
        details_row.addWidget(ev_box, 1)

        layout.addLayout(details_row, 1)

        # Copilot Metrics Bar
        self.copilot_metrics = QLabel("Copilot: Sẵn sàng  ·  Latency: —  ·  Tokens: —")
        self.copilot_metrics.setStyleSheet("color: #64748b; font-size: 11px;")
        layout.addWidget(self.copilot_metrics)

        return tab

    # -------------------------------------------------------------------------
    # Copilot Handlers & Actions
    # -------------------------------------------------------------------------
    def _on_opt_in_toggled(self, checked: bool) -> None:
        if checked and not self.claude_client.is_configured():
            QMessageBox.information(
                self,
                "API Key Required",
                "Vui lòng nhập Anthropic API Key hợp lệ để sử dụng Claude Meeting Copilot.",
            )

    def _on_api_key_changed(self, text: str) -> None:
        key = text.strip()
        self.claude_client.api_key = key
        self.cloud_opt_in.setChecked(bool(key and len(key) > 8))

    def _on_model_changed(self, model_name: str) -> None:
        self.claude_client.model = model_name

    def _toggle_key_visibility(self) -> None:
        if self.api_key_input.echoMode() == QLineEdit.EchoMode.Password:
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_toggle_key.setText("Ẩn Key")
        else:
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_toggle_key.setText("Hiện Key")

    def _add_knowledge_file(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Chọn tệp tài liệu hỗ trợ",
            "",
            "Documents (*.md *.markdown *.txt)",
        )
        for p in paths:
            self._index_knowledge_path(p)

    def _add_knowledge_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục tài liệu")
        if folder:
            self._index_knowledge_path(folder)

    def _clear_knowledge(self) -> None:
        self.knowledge_store.clear()
        self.knowledge_status.setText("Tài liệu (.md, .txt): 0 tệp (0 đoạn)")

    def _index_knowledge_path(self, path: str) -> None:
        self.knowledge_status.setText(f"Đang nạp: {Path(path).name}…")
        self.knowledge_worker = KnowledgeIndexWorker(self.knowledge_store, path)
        self.knowledge_worker.indexing_done.connect(self._on_indexing_done)
        self.knowledge_worker.indexing_failed.connect(lambda err: self.knowledge_status.setText(f"Lỗi nạp: {err}"))
        self.knowledge_worker.start()

    def _on_indexing_done(self, added: int, path: str) -> None:
        files = self.knowledge_store.get_loaded_files()
        chunks = self.knowledge_store.get_chunk_count()
        self.knowledge_status.setText(f"Tài liệu (.md, .txt): {len(files)} tệp ({chunks} đoạn)")

    def _review_context_snapshot(self) -> None:
        recent = self.context_store.get_recent_snapshot(seconds=180.0, max_segments=30)
        unconfirmed = self.english_live.text()
        formatted = MeetingContextStore.format_for_prompt(recent, unconfirmed)
        dlg = QDialog(self)
        dlg.setWindowTitle("Xem trước ngữ cảnh gửi tới Claude")
        dlg.resize(600, 450)
        l = QVBoxLayout(dlg)
        l.addWidget(QLabel("Dưới đây là nội dung trích đoạn gần nhất (~3 phút) sẽ được gửi kèm câu hỏi:"))
        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setPlainText(formatted if formatted else "Chưa có biên bản nào được ghi nhận.")
        l.addWidget(txt)
        btn = QPushButton("Đóng")
        btn.clicked.connect(dlg.accept)
        l.addWidget(btn)
        dlg.exec()

    def _clear_meeting_context(self) -> None:
        reply = QMessageBox.question(
            self,
            "Xác nhận xóa biên bản",
            "Bạn có chắc chắn muốn xóa toàn bộ ngữ cảnh cuộc họp hiện tại?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.context_store.clear()
            self.recent_thought_groups.clear()
            self.context_label.setText("Ngữ cảnh gần nhất: —")
            self.context_status.setText("Biên bản cuộc họp: 0 câu (0 từ)")

    def update_context_status(self) -> None:
        stats = self.context_store.get_context_summary()
        self.context_status.setText(
            f"Biên bản cuộc họp: {stats['total_segments']} câu ({stats['total_words']} từ)"
        )

    def _copy_english_answer(self) -> None:
        text = self.english_answer_view.toPlainText().strip()
        if text:
            QApplication.clipboard().setText(text)
            self.copilot_metrics.setText("Copilot: Đã sao chép câu trả lời tiếng Anh vào clipboard!")

    def _trigger_copilot(self, action_type: str) -> None:
        if not self.cloud_opt_in.isChecked():
            QMessageBox.warning(
                self,
                "Cloud Copilot Disabled",
                "Vui lòng bật 'Cho phép sử dụng Claude AI (Cloud Assistance Opt-In)' và cung cấp API Key trước khi gửi yêu cầu.",
            )
            return

        if not self.claude_client.is_configured():
            QMessageBox.warning(
                self,
                "API Key Missing",
                "Chưa có Anthropic API Key. Vui lòng nhập API Key để tiếp tục.",
            )
            return

        if self.copilot_worker and self.copilot_worker.isRunning():
            return  # Single in-flight request

        user_query = self.question_input.text().strip() or None
        unconfirmed = self.english_live.text().strip()

        # UI state during request
        self.btn_help_reply.setEnabled(False)
        self.btn_explain.setEnabled(False)
        self.btn_suggest.setEnabled(False)
        self.btn_cancel_copilot.setEnabled(True)
        self.english_answer_view.clear()
        self.vietnamese_meaning_view.clear()
        self.evidence_view.clear()
        self.copilot_metrics.setText(f"Copilot: Đang kết nối tới Claude Haiku ({action_type})…")

        self.copilot_worker = CopilotWorker(
            assistant=self.assistant,
            action_type=action_type,
            user_query=user_query,
            unconfirmed_live=unconfirmed,
        )
        self.copilot_worker.chunk_received.connect(self._on_copilot_token)
        self.copilot_worker.finished_success.connect(self._on_copilot_success)
        self.copilot_worker.failed_error.connect(self._on_copilot_error)
        self.copilot_worker.start()

    def _cancel_copilot(self) -> None:
        if self.copilot_worker and self.copilot_worker.isRunning():
            self.copilot_worker.cancel()
            self.copilot_metrics.setText("Copilot: Đã hủy yêu cầu.")
            self._reset_copilot_buttons()

    def _on_copilot_token(self, token: str) -> None:
        # Stream text progressively into the English answer view
        self.english_answer_view.insertPlainText(token)
        scrollbar = self.english_answer_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_copilot_success(self, result: CopilotResult) -> None:
        self.english_answer_view.setPlainText(result.english_answer)
        self.vietnamese_meaning_view.setPlainText(result.vietnamese_meaning)

        # Build evidence list with verified and unverified markers
        ev_lines = []
        if result.evidence_citations:
            ev_lines.append("Xác thực từ nguồn trích đoạn:")
            ev_lines.extend(f" • {c}" for c in result.evidence_citations)
        if result.unverified_citations:
            ev_lines.append("\nCảnh báo trích dẫn không có trong nguồn:")
            ev_lines.extend(f" ⚠️ {c}" for c in result.unverified_citations)
        if result.warnings:
            ev_lines.append("\nLưu ý & Điểm chưa rõ:")
            ev_lines.extend(f" ℹ️ {w}" for w in result.warnings)

        self.evidence_view.setPlainText("\n".join(ev_lines) if ev_lines else "Không có trích dẫn bổ sung.")

        usage = result.usage
        self.copilot_metrics.setText(
            f"Copilot: Hoàn thành ({usage.model}) · TTFT: {usage.time_to_first_token:.2f}s · "
            f"Tổng: {usage.total_duration:.2f}s · In/Out: {usage.input_tokens}/{usage.output_tokens} tokens"
        )
        self._reset_copilot_buttons()

    def _on_copilot_error(self, err_msg: str) -> None:
        self.copilot_metrics.setText(f"Copilot lỗi: {err_msg}")
        self.vietnamese_meaning_view.setPlainText(f"Lỗi xử lý yêu cầu: {err_msg}")
        self._reset_copilot_buttons()

    def _reset_copilot_buttons(self) -> None:
        self.btn_help_reply.setEnabled(True)
        self.btn_explain.setEnabled(True)
        self.btn_suggest.setEnabled(True)
        self.btn_cancel_copilot.setEnabled(False)

    # -------------------------------------------------------------------------
    # Window Controls & Live Audio Lifecycle
    # -------------------------------------------------------------------------
    def toggle_top(self, enabled: bool) -> None:
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
        self.show()

    def post(self, kind: str, data: dict) -> None:
        try:
            self.events.put_nowait((kind, data))
        except queue.Full:
            if kind in {"english_partial", "vietnamese_partial", "trace"}:
                return  # A newer partial will replace this one
            print(f"UI_QUEUE_FULL kind={kind}; stopping to avoid losing a final subtitle", flush=True)
            self.event_overflow.set()
            self.stop_event.set()

    def start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        if self.input.currentData() is None or self.output.currentData() is None:
            self.status.setText("BlackHole input or headphone output is missing")
            return
        self.stop_event = threading.Event()
        self.event_overflow.clear()
        self.final_en.clear()
        self.final_vi.clear()
        self.current_id = None
        self.final_en_ids.clear()
        self.final_vi_ids.clear()
        self.vi_revisions.clear()
        self.preview_id = None
        self.first_english.clear()
        self.first_vietnamese_rendered.clear()
        self.first_vietnamese_received.clear()
        self.traces.clear()
        self.recent_thought_groups.clear()
        self.results.clear()
        self.coverage = dict.fromkeys(self.coverage, 0)
        self.english.clear()
        self.vietnamese.clear()
        self.context_label.setText("Ngữ cảnh gần nhất: —")
        self.english_live.setText("Waiting for speech…")
        self.vietnamese_live.setText("Đang lắng nghe cuộc họp…")
        self.metrics.setText("Audio → first EN: —  ·  first VI: —  ·  final VI: —")
        self.context_store.clear()
        self.update_context_status()

        input_id = self.input.currentData()
        output_id = self.output.currentData()
        input_name = engine.sd.query_devices(input_id)["name"]
        output_name = engine.sd.query_devices(output_id)["name"]
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status.setText("Starting local models…")

        def work() -> None:
            try:
                cfg = engine.Config(input_id, input_name, output_id, output_name, 48_000,
                                    4.0, 0.004, "", engine.prepare_whisper(engine.WHISPER_MODEL),
                                    engine.TRANSLATION_MODEL, True, 12.0,
                                    engine.device_identity(output_id))
                live_pipeline.run(cfg, self.post, self.stop_event)
            except Exception as exc:
                self.post("status", {"text": f"Error: {exc}"})
            finally:
                self.post("stopped", {})

        self.worker = threading.Thread(target=work, name="translator-ui-worker", daemon=True)
        self.worker.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.status.setText("Stopping…")

    @staticmethod
    def show_history(view: QTextEdit, lines: list[str]) -> None:
        scrollbar = view.verticalScrollBar()
        old_position = scrollbar.value()
        old_maximum = scrollbar.maximum()
        view.setPlainText("\n".join(lines))
        if old_position:
            scrollbar.setValue(old_position + scrollbar.maximum() - old_maximum)
        else:
            scrollbar.setValue(0)

    def drain(self) -> None:
        if self.event_overflow.is_set():
            self.status.setText("Error: UI event queue full; session stopped")
        while True:
            try:
                kind, data = self.events.get_nowait()
            except queue.Empty:
                return

            if kind == "english_partial" and data["id"] not in self.final_en_ids:
                if self.current_id is not None and data["id"] < self.current_id:
                    continue
                self.current_id = data["id"]
                self.first_english.setdefault(data["id"], data["latency"])
                stable = data["stable"]
                is_fill = data.get("is_filler", False)
                if not is_fill:
                    self.english_live.setText(f"Hearing: {data['text']}  |  Stable: {stable}")
                rendered_vi = self.first_vietnamese_rendered.get(data["id"])
                vi_str = f"{rendered_vi:.2f}s" if rendered_vi is not None else "—"
                self.metrics.setText(f"Audio → first EN: {self.first_english[data['id']]:.2f}s  ·  first VI: {vi_str}  ·  final VI: —")

            elif kind == "english_final" and data["id"] not in self.final_en_ids:
                self.first_english.setdefault(data["id"], data["latency"])
                self.final_en_ids.add(data["id"])
                self.current_id = data["id"]
                is_fill = data.get("is_filler", False)
                tag = f"[{data['id']}]" + (" (filler)" if is_fill else "")
                self.final_en.insert(0, f"{tag} {data['text']}")
                del self.final_en[150:]
                self.show_history(self.english, self.final_en)
                if not is_fill:
                    self.english_live.setText(f"Completed: {data['text']}")
                rendered_vi = self.first_vietnamese_rendered.get(data["id"])
                vi_str = f"{rendered_vi:.2f}s" if rendered_vi is not None else "—"
                self.metrics.setText(f"Audio → first EN: {self.first_english[data['id']]:.2f}s  ·  first VI: {vi_str}  ·  final VI: —")
                self.status.setText(f"Listening · final English {data['latency']:.1f}s")

                # Feed finalized English into Meeting Context Store for Copilot
                self.context_store.add_segment(
                    segment_id=data["id"],
                    text=data["text"],
                    is_filler=is_fill,
                )
                self.update_context_status()

            elif kind == "translation_revision":
                print(f"REVISION id={data['id']} version={data['revision']}", flush=True)
                if data["revision"] > self.vi_revisions.get(data["id"], -1):
                    self.vi_revisions[data["id"]] = data["revision"]
                    if self.preview_id == data["id"]:
                        preview = data.get("preview", "")
                        if preview:
                            self.vietnamese_live.setText(f"[{data['id']}] Bản nháp · {preview}")
                        else:
                            self.vietnamese_live.setText("Đang dịch…")

            elif kind == "vietnamese_partial" and data["id"] not in self.final_vi_ids:
                if data.get("revision", 0) < self.vi_revisions.get(data["id"], -1):
                    continue
                self.vi_revisions[data["id"]] = data.get("revision", 0)
                if self.preview_id is not None and data["id"] < self.preview_id:
                    continue
                self.preview_id = data["id"]
                now = time.monotonic()
                if not data.get("is_filler", False):
                    self.vietnamese_live.setText(f"[{data['id']}] Bản nháp · {data['text']}")
                self.first_vietnamese_received.setdefault(data["id"], data["latency"])
                trace = self.traces.setdefault(data["id"], {})
                origin = trace.get("source_start")
                if data["id"] not in self.first_vietnamese_rendered:
                    rendered_lat = (now - origin) if origin is not None else data["latency"]
                    self.first_vietnamese_rendered[data["id"]] = rendered_lat
                    trace.setdefault("first_token_rendered", now)
                first_en = self.first_english.get(data["id"])
                rendered_lat = self.first_vietnamese_rendered[data["id"]]
                en_str = f"{first_en:.2f}s" if first_en is not None else "—"
                self.metrics.setText(f"Audio → first EN: {en_str}  ·  first VI: {rendered_lat:.2f}s  ·  final VI: —")

            elif kind == "vietnamese_cancelled":
                if self.preview_id == data["id"]:
                    self.vietnamese_live.setText("Đang lắng nghe cuộc họp…")
                    self.preview_id = None

            elif kind == "vietnamese_final" and data["id"] not in self.final_vi_ids:
                self.final_vi_ids.add(data["id"])
                now = time.monotonic()
                is_fill = data.get("is_filler", False)
                tag = f"[{data['id']}]" + (" (filler)" if is_fill else "")
                self.final_vi.insert(0, f"{tag} {data['text']}")
                del self.final_vi[150:]
                self.show_history(self.vietnamese, self.final_vi)

                if not is_fill:
                    self.recent_thought_groups.append(f"[{data['id']}] {data['text']}")
                    self.context_label.setText("Ngữ cảnh gần nhất: " + "  •  ".join(self.recent_thought_groups))
                    if self.preview_id == data["id"]:
                        self.vietnamese_live.setText(f"[{data['id']}] Hoàn tất · {data['text']}")
                        self.preview_id = None

                first_rendered = self.first_vietnamese_rendered.get(data["id"])
                if first_rendered is None:
                    first_rendered = data["latency"]
                    self.first_vietnamese_rendered[data["id"]] = first_rendered
                    self.traces.setdefault(data["id"], {}).setdefault("first_token_rendered", now)
                first_received = self.first_vietnamese_received.get(
                    data["id"], data.get("first_token_received_latency", first_rendered)
                )
                first_en = self.first_english.get(data["id"])
                if first_en is not None:
                    self.metrics.setText(f"Audio → first EN: {first_en:.2f}s  ·  first VI: {first_rendered:.2f}s  ·  final VI: {data['latency']:.2f}s")
                    self.results.append((first_en, first_rendered, data["latency"], first_received or first_rendered))
                    print(f"METRIC id={data['id']} audio_to_first_en={first_en:.3f}s "
                          f"audio_to_first_vi_rendered={first_rendered:.3f}s "
                          f"audio_to_first_vi_received={first_received if first_received is not None else first_rendered:.3f}s "
                          f"audio_to_final_vi={data['latency']:.3f}s", flush=True)
                    trace = self.traces.get(data["id"], {})
                    origin = trace.get("source_start")
                    if origin is not None:
                        def elapsed(stage: str) -> str:
                            value = trace.get(stage)
                            return f"{value - origin:.3f}" if value is not None else "—"
                        queued, dequeued = trace.get("queued"), trace.get("dequeued")
                        wait = f"{dequeued - queued:.3f}" if queued is not None and dequeued is not None else "—"
                        req_start, done = trace.get("request_start"), trace.get("translation_done")
                        req_dur = f"{done - req_start:.3f}" if req_start is not None and done is not None else "—"
                        print(f"TRACE id={data['id']} first_en_ready={elapsed('first_en_ready')} "
                              f"stable={elapsed('stable')} eligible={elapsed('eligible')} "
                              f"final_en={elapsed('final_en')} queue_wait={wait} "
                              f"request_start={elapsed('request_start')} "
                              f"first_token_received={elapsed('first_token_received')} "
                              f"first_token_rendered={elapsed('first_token_rendered')} "
                              f"request_duration={req_dur}", flush=True)
                self.status.setText(f"Listening · first token {first_rendered:.1f}s · final {data['latency']:.1f}s")

            elif kind == "trace":
                trace = self.traces.setdefault(data["id"], {})
                trace.setdefault("source_start", data["source_start"])
                trace.setdefault(data["stage"], data["at"])
                if "fragment_id" in data or "stable_wait" in data or "request_duration" in data or "duration" in data:
                    extra = " ".join(f"{name}={value:.3f}s" if name in {"stable_wait", "queue_wait", "request_duration", "duration"}
                                     else f"{name}={value}" for name, value in data.items()
                                     if name in {"fragment_id", "revision", "stable_wait", "queue_wait", "queue_size", "request_duration", "duration"})
                    print(f"TRACE id={data['id']} stage={data['stage']} "
                          f"audio_elapsed={data['at'] - data['source_start']:.3f}s {extra}", flush=True)

            elif kind == "coverage":
                print(f"COVERAGE id={data['id']} fragment={data['fragment_id']} "
                      f"english_words={data['words']} backlog={data['queue_size']}", flush=True)

            elif kind == "coverage_final":
                for name in ("english_words", "covered_words", "fragments", "revisions"):
                    self.coverage[name] += data[name]
                print(f"COVERAGE_FINAL id={data['id']} english_words={data['english_words']} "
                      f"covered_words={data['covered_words']} fragments={data['fragments']} "
                      f"revisions={data['revisions']}", flush=True)

            elif kind == "translation_delayed":
                self.status.setText(f"Listening · translation queue wait {data['wait']:.1f}s")

            elif kind == "ollama_stats":
                frag_info = f" fragment={data['fragment_id']}" if "fragment_id" in data else ""
                print(f"OLLAMA id={data['id']}{frag_info} load={data['load_ms']:.1f}ms prompt={data['prompt_ms']:.1f}ms eval={data['eval_ms']:.1f}ms", flush=True)

            elif kind == "translation_skipped":
                self.coverage["skipped"] += 1
                print(f"SKIPPED id={data['id']} reason={data['reason']}", flush=True)
                if data["reason"] in {"audio overflow", "queue full; stopping to avoid lost words"}:
                    self.status.setText(f"Listening · skipped speech: {data['reason']}")

            elif kind == "health" and any(data["dropped"].values()):
                self.status.setText(f"Listening · dropped {data['dropped']} · translation backlog {data['translation_backlog']}")

            elif kind == "status":
                self.status.setText(data["text"])

            elif kind == "stopped":
                self.vietnamese_live.setText("Stopped")
                self.english_live.setText("")
                self.preview_id = None
                if self.results:
                    columns = list(zip(*self.results))
                    def p95(values: tuple[float, ...]) -> float:
                        ordered = sorted(values)
                        return ordered[max(0, int(0.95 * len(ordered) + 0.999) - 1)]
                    names = ("first_en", "first_vi_rendered", "final_vi", "first_vi_received")
                    print(f"BENCHMARK n={len(self.results)} " + " ".join(
                        f"{name}_p50={statistics.median(values):.3f}s {name}_p95={p95(values):.3f}s"
                        for name, values in zip(names, columns)), flush=True)
                print("COVERAGE_SUMMARY " + " ".join(f"{key}={value}"
                      for key, value in self.coverage.items()), flush=True)
                self.start_button.setEnabled(True)
                self.stop_button.setEnabled(False)
                if not self.status.text().startswith("Error:"):
                    self.status.setText("Stopped")

    def closeEvent(self, event) -> None:
        self.stop_event.set()
        if self.worker and self.worker.is_alive():
            self.worker.join(timeout=2)
        if self.copilot_worker and self.copilot_worker.isRunning():
            self.copilot_worker.cancel()
            self.copilot_worker.wait(1000)
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    window = Window()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
