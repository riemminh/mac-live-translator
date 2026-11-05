"""Main application window composing translation and Copilot tabs and coordinating runtime lifecycle."""

from __future__ import annotations

import os
import queue
import threading
from collections import deque

import sounddevice as sd
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QMainWindow, QTabWidget, QVBoxLayout, QWidget

from mac_live_translator.asr.whisper import prepare_whisper
from mac_live_translator.audio.devices import device_identity
from mac_live_translator.config import Config, TRANSLATION_MODEL, WHISPER_MODEL
from mac_live_translator.copilot.assistant import MeetingAssistant
from mac_live_translator.copilot.client import ClaudeClient
from mac_live_translator.gui.copilot_actions import CopilotActionsHandler
from mac_live_translator.gui.copilot_tab import create_copilot_tab
from mac_live_translator.gui.translation_events import handle_translation_event
from mac_live_translator.gui.translation_tab import create_translation_tab
from mac_live_translator.gui.workers import CopilotWorker, KnowledgeIndexWorker
from mac_live_translator.knowledge.store import KnowledgeStore
from mac_live_translator.meeting.context import MeetingContextStore
from mac_live_translator.pipeline.live import run as run_pipeline


class Window(QMainWindow):
    """Bilingual desktop application window for Live Translation and Meeting Copilot."""

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
        self.coverage = {"english_words": 0, "covered_words": 0, "fragments": 0, "revisions": 0, "skipped": 0}

        # Meeting Copilot Subsystems
        self.context_store = MeetingContextStore(max_entries=1500)
        self.knowledge_store = KnowledgeStore()
        self.claude_client = ClaudeClient(api_key=os.environ.get("ANTHROPIC_API_KEY", "").strip())
        self.assistant = MeetingAssistant(self.context_store, self.knowledge_store, self.claude_client)
        self.copilot_worker: CopilotWorker | None = None
        self.indexing_workers: set[KnowledgeIndexWorker] = set()
        self.copilot_generation_id = 0
        self.copilot_actions = CopilotActionsHandler(self)

        # Build UI Tabs
        root = QWidget()
        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(6)

        self.tabs = QTabWidget()
        self.translation_tab = create_translation_tab(self)
        self.copilot_tab = create_copilot_tab(self)
        self.tabs.addTab(self.translation_tab, "🎧 Live Translation (Trực tiếp)")
        self.tabs.addTab(self.copilot_tab, "🤖 Meeting Copilot (Trợ lý trả lời)")
        main_layout.addWidget(self.tabs)

        self.setCentralWidget(root)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.drain)
        self.timer.start(50)

    def toggle_top(self, checked: bool) -> None:
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, checked)
        self.show()

    def post(self, kind: str, data: dict) -> None:
        try:
            self.events.put_nowait((kind, data))
        except queue.Full:
            if kind in {"status", "stopped", "vietnamese_partial", "english_partial"}:
                return
            print(f"UI_QUEUE_FULL kind={kind}; stopping to avoid losing a final subtitle", flush=True)
            self.event_overflow.set()
            self.stop_event.set()

    def drain(self) -> None:
        if self.event_overflow.is_set():
            self.status.setText("Error: UI event queue full; session stopped")
        while True:
            try:
                kind, data = self.events.get_nowait()
            except queue.Empty:
                return
            handle_translation_event(self, kind, data)

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
        self.copilot_actions.update_context_status()
        self.copilot_generation_id += 1
        if self.copilot_worker and self.copilot_worker.isRunning():
            self.copilot_worker.cancel()
            self.copilot_actions.reset_copilot_buttons()

        input_id = self.input.currentData()
        output_id = self.output.currentData()
        input_name = sd.query_devices(input_id)["name"]
        output_name = sd.query_devices(output_id)["name"]
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status.setText("Starting local models…")

        def work() -> None:
            try:
                cfg = Config(
                    input_device=input_id,
                    input_name=input_name,
                    output_device=output_id,
                    output_name=output_name,
                    sample_rate=48_000,
                    chunk_seconds=4.0,
                    min_rms=0.004,
                    voice="",
                    whisper_model=prepare_whisper(WHISPER_MODEL),
                    translation_model=TRANSLATION_MODEL,
                    speak=False,
                    max_lag=12.0,
                    output_identity=device_identity(output_id),
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
        if self.copilot_worker and self.copilot_worker.isRunning():
            self.copilot_worker.cancel()
            self.copilot_worker.wait(1000)
        for kw in list(self.indexing_workers):
            if kw.isRunning():
                kw.wait(1000)
        super().closeEvent(event)

