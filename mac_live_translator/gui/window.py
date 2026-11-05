"""Main application window uniting live translation and Meeting Copilot in a native macOS workspace."""

from __future__ import annotations

import os
import queue
import threading
import sounddevice as sd
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QMainWindow, QSplitter, QVBoxLayout, QWidget

from mac_live_translator.asr.whisper import prepare_whisper
from mac_live_translator.audio.devices import device_identity
from mac_live_translator.config import Config, TRANSLATION_MODEL, WHISPER_MODEL
from mac_live_translator.context_service.engine import ContextEngine
from mac_live_translator.copilot.assistant import MeetingAssistant
from mac_live_translator.copilot.client import ClaudeClient
from mac_live_translator.gui.copilot_actions import CopilotActionsHandler
from mac_live_translator.gui.copilot_panel import create_copilot_panel
from mac_live_translator.gui.subtitle_state import SubtitleState
from mac_live_translator.gui.theme import DARK_THEME_QSS
from mac_live_translator.gui.top_bar import create_top_bar
from mac_live_translator.gui.translation_events import handle_translation_event
from mac_live_translator.gui.translation_panel import create_translation_panel
from mac_live_translator.gui.understanding_controller import UnderstandingController
from mac_live_translator.gui.workers import CompactionWorker, CopilotWorker, KnowledgeIndexWorker
from mac_live_translator.knowledge.store import KnowledgeStore
from mac_live_translator.meeting.context import MeetingContextStore
from mac_live_translator.meeting.memory_store import CompactedMemoryStore
from mac_live_translator.pipeline.live import run as run_pipeline


class Window(QMainWindow):
    """Unified desktop meeting workspace with continuous live translation and Meeting Understanding."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("🎧 Mac Live Translator & Meeting Copilot")
        self.resize(1260, 820)
        self.setMinimumSize(960, 640)
        self.setStyleSheet(DARK_THEME_QSS)

        # Pipeline queues and stores
        self.events: queue.Queue[tuple[str, dict]] = queue.Queue(maxsize=512)
        self.event_overflow, self.stop_event, self.worker = threading.Event(), threading.Event(), None
        self._init_session_state()

        self.context_store = MeetingContextStore(max_entries=1500)
        self.memory_store = CompactedMemoryStore(protect_recent=30)
        self.knowledge_store = KnowledgeStore()
        self.claude_client = ClaudeClient(api_key=os.environ.get("ANTHROPIC_API_KEY", "").strip())
        self.assistant = MeetingAssistant(self.context_store, self.knowledge_store, self.claude_client, self.memory_store)
        self.context_engine = ContextEngine(
            client=self.claude_client, default_context_store=self.context_store, default_memory_store=self.memory_store
        )
        self.understanding_controller = UnderstandingController(self)
        self.copilot_worker, self.compaction_worker = None, None
        self.indexing_workers: set[KnowledgeIndexWorker] = set()
        self.copilot_generation_id, self.last_prepared_request = 0, None
        self.copilot_actions = CopilotActionsHandler(self)

        # Composition
        root = QWidget()
        root.setObjectName("rootWidget")
        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(10)
        main_layout.addWidget(create_top_bar(self))

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(create_translation_panel(self))
        self.splitter.addWidget(create_copilot_panel(self))
        self.splitter.setStretchFactor(0, 55)
        self.splitter.setStretchFactor(1, 45)
        self.splitter.setSizes([690, 550])
        main_layout.addWidget(self.splitter, 1)

        self.setCentralWidget(root)
        self._bind_events()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.drain)
        self.timer.start(50)

    def _init_session_state(self) -> None:
        self.final_en, self.final_vi, self.final_bi = [], [], []
        self.current_id = self.preview_id = None
        self.final_en_ids, self.final_vi_ids = set(), set()
        self.vi_revisions, self.traces, self.first_english = {}, {}, {}
        self.first_vietnamese_draft, self.first_vietnamese_rendered, self.first_vietnamese_received = {}, {}, {}
        self.subtitle_state = SubtitleState()
        self.results, self.fast_preview_enabled = [], True
        self.coverage = {"english_words": 0, "covered_words": 0, "fragments": 0, "revisions": 0, "skipped": 0}

    def _bind_events(self) -> None:
        c, u = self.copilot_actions, self.understanding_controller
        self.btn_help_reply.clicked.connect(lambda: c.trigger_copilot("help_me_reply"))
        self.btn_explain.clicked.connect(lambda: c.trigger_copilot("explain_context"))
        self.btn_suggest.clicked.connect(lambda: c.trigger_copilot("suggest_question"))
        self.btn_cancel_copilot.clicked.connect(c.cancel_copilot)
        self.btn_copy_english.clicked.connect(c.copy_english_answer)
        self.cloud_opt_in.toggled.connect(c.on_opt_in_toggled)
        self.model_combo.currentTextChanged.connect(c.on_model_changed)
        self.understanding_opt_in.toggled.connect(u.on_opt_in_toggled)
        self.freeze_checkbox.toggled.connect(u.on_freeze_toggled)
        self.btn_catchup.clicked.connect(u.on_catchup_clicked)
        u.bind_ui()

    def toggle_top(self, checked: bool) -> None:
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, checked)
        self.show()

    def post(self, kind: str, data: dict) -> None:
        try:
            self.events.put_nowait((kind, data))
        except queue.Full:
            if kind not in {"status", "stopped", "vietnamese_partial", "english_partial"}:
                self.event_overflow.set()
                self.stop_event.set()

    def drain(self) -> None:
        while True:
            try:
                kind, data = self.events.get_nowait()
            except queue.Empty:
                return
            handle_translation_event(self, kind, data)

    def start(self) -> None:
        if (self.worker and self.worker.is_alive()) or self.input.currentData() is None or self.output.currentData() is None:
            return
        self.stop_event, self.event_overflow = threading.Event(), threading.Event()
        self._init_session_state()
        for v in (self.english, self.vietnamese, self.bilingual):
            v.clear()
        self.subtitle_state.reset()
        self.english_live.setText("Waiting for speech…")
        self.vietnamese_live.setText("Đang lắng nghe cuộc họp…")
        if hasattr(self, "compact_vi_live"):
            self.compact_vi_live.setText("Đang lắng nghe cuộc họp…")
        if hasattr(self, "recent_captions_label"):
            self.recent_captions_label.setText("Chưa có phụ đề hoàn tất gần đây.")
        if hasattr(self, "listening_badge"):
            self.listening_badge.setText("🟢 Đang nghe (Listening)")
        self.context_store.clear()
        self.memory_store.clear()
        self.context_engine.reset_session("default")
        self.understanding_controller.reset()
        self.copilot_actions.update_context_status()
        self.copilot_generation_id += 1
        self.last_prepared_request = None
        for w in (self.copilot_worker, self.compaction_worker):
            if w and w.isRunning():
                w.cancel()
        if self.copilot_worker and self.copilot_worker.isRunning():
            self.copilot_actions.reset_copilot_buttons()

        in_id, out_id = self.input.currentData(), self.output.currentData()
        in_name, out_name = sd.query_devices(in_id)["name"], sd.query_devices(out_id)["name"]
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status.setText("Starting local models…")

        def work() -> None:
            try:
                cfg = Config(
                    input_device=in_id, input_name=in_name, output_device=out_id, output_name=out_name,
                    sample_rate=48_000, chunk_seconds=4.0, min_rms=0.004, voice="",
                    whisper_model=prepare_whisper(WHISPER_MODEL), translation_model=TRANSLATION_MODEL,
                    speak=False, max_lag=12.0, output_identity=device_identity(out_id),
                    fast_preview=self.fast_preview_enabled,
                )
                run_pipeline(cfg, self.post, self.stop_event)
            except Exception as exc:
                self.post("status", {"text": f"Error: {exc}"})
            finally:
                self.post("stopped", {})

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.status.setText("Stopping…")

    def closeEvent(self, event) -> None:
        self.stop_event.set()
        if self.worker and self.worker.is_alive():
            self.worker.join(timeout=2)
        self.understanding_controller.reset()
        for w in (self.copilot_worker, self.compaction_worker, *self.indexing_workers):
            if w and w.isRunning():
                if hasattr(w, "cancel"):
                    w.cancel()
                w.wait(1000)
        super().closeEvent(event)
