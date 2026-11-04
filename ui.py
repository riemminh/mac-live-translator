"""Small desktop view over the local capture and translation pipeline."""

from __future__ import annotations

import queue
import statistics
import sys
import threading
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QHBoxLayout,
                               QLabel, QMainWindow, QPushButton, QTextEdit,
                               QVBoxLayout, QWidget)

import main as engine
import live_pipeline


class Window(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Mac Live Translator")
        self.resize(760, 540)
        self.events: queue.Queue[tuple[str, dict]] = queue.Queue(maxsize=128)
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.final_en: list[str] = []
        self.final_vi: list[str] = []
        self.current_id = None
        self.final_en_ids: set[int] = set()
        self.final_vi_ids: set[int] = set()
        self.first_english: dict[int, float] = {}
        self.first_vietnamese: dict[int, float] = {}
        self.traces: dict[int, dict[str, float]] = {}
        self.results: list[tuple[float, float, float]] = []

        root = QWidget()
        layout = QVBoxLayout(root)
        row = QHBoxLayout()
        self.input = QComboBox()
        self.input.setMinimumWidth(250)
        self.output = QComboBox()
        self.output.setMinimumWidth(250)
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
        layout.addWidget(self.status)
        self.metrics = QLabel("Audio → first EN: —  ·  first VI: —  ·  final VI: —")
        layout.addWidget(self.metrics)
        self.english = QTextEdit()
        self.english.setReadOnly(True)
        self.vietnamese = QTextEdit()
        self.vietnamese.setReadOnly(True)
        layout.addWidget(QLabel("English transcript"))
        self.english_live = QLabel("")
        self.english_live.setWordWrap(True)
        layout.addWidget(self.english_live)
        layout.addWidget(self.english)
        layout.addWidget(QLabel("Vietnamese translation"))
        self.vietnamese_live = QLabel("")
        self.vietnamese_live.setWordWrap(True)
        layout.addWidget(self.vietnamese_live)
        layout.addWidget(self.vietnamese)
        controls = QHBoxLayout()
        self.start_button = QPushButton("Start")
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
        self.setCentralWidget(root)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.drain)
        self.timer.start(50)

    def toggle_top(self, enabled: bool) -> None:
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
        self.show()

    def post(self, kind: str, data: dict) -> None:
        try:
            self.events.put_nowait((kind, data))
        except queue.Full:
            try:
                self.events.get_nowait()
                self.events.put_nowait((kind, data))
            except queue.Empty:
                pass

    def start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        if self.input.currentData() is None or self.output.currentData() is None:
            self.status.setText("BlackHole input or headphone output is missing")
            return
        self.stop_event = threading.Event()
        self.final_en.clear()
        self.final_vi.clear()
        self.current_id = None
        self.final_en_ids.clear()
        self.final_vi_ids.clear()
        self.first_english.clear()
        self.first_vietnamese.clear()
        self.traces.clear()
        self.results.clear()
        self.english.clear()
        self.vietnamese.clear()
        self.english_live.clear()
        self.vietnamese_live.clear()
        self.metrics.setText("Audio → first EN: —  ·  first VI: —  ·  final VI: —")
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

    def drain(self) -> None:
        while True:
            try:
                kind, data = self.events.get_nowait()
            except queue.Empty:
                return
            if kind == "english_partial" and data["id"] not in self.final_en_ids:
                self.first_english.setdefault(data["id"], data["latency"])
                self.current_id = data["id"]
                stable = data["stable"]
                self.english_live.setText(f"Stable: {stable}  |  Hearing: {data['text']}")
                self.metrics.setText(f"Audio → first EN: {self.first_english[data['id']]:.2f}s  ·  first VI: —  ·  final VI: —")
            elif kind == "english_final" and data["id"] not in self.final_en_ids:
                self.first_english.setdefault(data["id"], data["latency"])
                self.final_en_ids.add(data["id"])
                self.current_id = data["id"]
                self.final_en.append(f"[{data['id']}] {data['text']}")
                self.english.setPlainText("\n".join(self.final_en[-100:]))
                self.english_live.clear()
                self.metrics.setText(f"Audio → first EN: {self.first_english[data['id']]:.2f}s  ·  first VI: —  ·  final VI: —")
                self.status.setText(f"Listening · final English {data['latency']:.1f}s")
            elif kind == "vietnamese_partial" and data["id"] not in self.final_vi_ids:
                self.vietnamese_live.setText(f"[{data['id']}] … {data['text']}")
                self.first_vietnamese.setdefault(data["id"], data["latency"])
                self.traces.setdefault(data["id"], {}).setdefault("first_token_rendered", time.monotonic())
                first_en = self.first_english.get(data["id"])
                self.metrics.setText(f"Audio → first EN: {first_en:.2f}s  ·  first VI: {self.first_vietnamese[data['id']]:.2f}s  ·  final VI: —" if first_en is not None else "Audio → first EN: —  ·  first VI: —  ·  final VI: —")
            elif kind == "vietnamese_cancelled":
                if self.vietnamese_live.text().startswith(f"[{data['id']}]"):
                    self.vietnamese_live.clear()
            elif kind == "vietnamese_final" and data["id"] not in self.final_vi_ids:
                self.final_vi_ids.add(data["id"])
                self.final_vi.append(f"[{data['id']}] {data['text']}")
                self.vietnamese.setPlainText("\n".join(self.final_vi[-100:]))
                self.vietnamese_live.clear()
                first = self.first_vietnamese.get(data["id"], data["first_token_latency"])
                first_en = self.first_english.get(data["id"])
                if first is not None and first_en is not None:
                    self.metrics.setText(f"Audio → first EN: {first_en:.2f}s  ·  first VI: {first:.2f}s  ·  final VI: {data['latency']:.2f}s")
                    self.results.append((first_en, first, data["latency"]))
                    print(f"METRIC id={data['id']} audio_to_first_en={first_en:.3f}s audio_to_first_vi={first:.3f}s audio_to_final_vi={data['latency']:.3f}s", flush=True)
                    trace = self.traces.get(data["id"], {})
                    origin = trace.get("source_start")
                    if origin is not None:
                        def elapsed(stage: str) -> str:
                            value = trace.get(stage)
                            return f"{value - origin:.3f}" if value is not None else "—"
                        queued, dequeued = trace.get("queued"), trace.get("dequeued")
                        wait = f"{dequeued - queued:.3f}" if queued is not None and dequeued is not None else "—"
                        print(f"TRACE id={data['id']} first_en_ready={elapsed('first_en_ready')} "
                              f"stable={elapsed('stable')} eligible={elapsed('eligible')} "
                              f"final_en={elapsed('final_en')} queue_wait={wait} "
                              f"request_start={elapsed('request_start')} "
                              f"first_token_received={elapsed('first_token_received')} "
                              f"first_token_rendered={elapsed('first_token_rendered')}", flush=True)
                self.status.setText(f"Listening · first token {first:.1f}s · final {data['latency']:.1f}s" if first is not None else "Listening")
            elif kind == "trace":
                trace = self.traces.setdefault(data["id"], {})
                trace.setdefault("source_start", data["source_start"])
                trace.setdefault(data["stage"], data["at"])
            elif kind == "ollama_stats":
                print(f"OLLAMA id={data['id']} load={data['load_ms']:.1f}ms prompt={data['prompt_ms']:.1f}ms eval={data['eval_ms']:.1f}ms", flush=True)
            elif kind == "translation_skipped":
                print(f"SKIPPED id={data['id']} reason={data['reason']}", flush=True)
            elif kind == "health" and any(data["dropped"].values()):
                self.status.setText(f"Listening · dropped {data['dropped']}")
            elif kind == "status":
                self.status.setText(data["text"])
            elif kind == "stopped":
                if self.results:
                    columns = list(zip(*self.results))
                    def p95(values: tuple[float, ...]) -> float:
                        ordered = sorted(values)
                        return ordered[max(0, int(0.95 * len(ordered) + 0.999) - 1)]
                    print(f"BENCHMARK n={len(self.results)} " + " ".join(
                        f"{name}_p50={statistics.median(values):.3f}s {name}_p95={p95(values):.3f}s"
                        for name, values in zip(("first_en", "first_vi", "final_vi"), columns)), flush=True)
                self.start_button.setEnabled(True)
                self.stop_button.setEnabled(False)
                if not self.status.text().startswith("Error:"):
                    self.status.setText("Stopped")

    def closeEvent(self, event) -> None:
        self.stop_event.set()
        if self.worker and self.worker.is_alive():
            self.worker.join(timeout=2)
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    window = Window()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
