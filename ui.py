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
        # Stores (first_en, first_vi_rendered, final_vi, first_vi_received)
        self.results: list[tuple[float, float, float, float]] = []
        self.coverage = {"english_words": 0, "covered_words": 0,
                         "fragments": 0, "revisions": 0, "skipped": 0}

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
        layout.addWidget(QLabel("Vietnamese translation"))
        self.vietnamese_live = QLabel("")
        self.vietnamese_live.setWordWrap(True)
        layout.addWidget(self.vietnamese_live)
        layout.addWidget(self.vietnamese)
        layout.addWidget(QLabel("English transcript"))
        self.english_live = QLabel("")
        self.english_live.setWordWrap(True)
        layout.addWidget(self.english_live)
        layout.addWidget(self.english)
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
            if kind in {"english_partial", "vietnamese_partial", "trace"}:
                return  # A newer partial will replace this one.
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
        self.results.clear()
        self.coverage = dict.fromkeys(self.coverage, 0)
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

    @staticmethod
    def show_history(view: QTextEdit, lines: list[str]) -> None:
        scrollbar = view.verticalScrollBar()
        old_position = scrollbar.value()
        old_maximum = scrollbar.maximum()
        view.setPlainText("\n".join(lines))
        # Follow the newest entry at the top; retain the reader's place when
        # they have scrolled down into older entries.
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
                self.english_live.setText(f"Stable: {stable}  |  Hearing: {data['text']}")
                rendered_vi = self.first_vietnamese_rendered.get(data["id"])
                vi_str = f"{rendered_vi:.2f}s" if rendered_vi is not None else "—"
                self.metrics.setText(f"Audio → first EN: {self.first_english[data['id']]:.2f}s  ·  first VI: {vi_str}  ·  final VI: —")
            elif kind == "english_final" and data["id"] not in self.final_en_ids:
                self.first_english.setdefault(data["id"], data["latency"])
                self.final_en_ids.add(data["id"])
                self.current_id = data["id"]
                self.final_en.insert(0, f"[{data['id']}] {data['text']}")
                del self.final_en[100:]
                self.show_history(self.english, self.final_en)
                self.english_live.clear()
                rendered_vi = self.first_vietnamese_rendered.get(data["id"])
                vi_str = f"{rendered_vi:.2f}s" if rendered_vi is not None else "—"
                self.metrics.setText(f"Audio → first EN: {self.first_english[data['id']]:.2f}s  ·  first VI: {vi_str}  ·  final VI: —")
                self.status.setText(f"Listening · final English {data['latency']:.1f}s")
            elif kind == "translation_revision":
                print(f"REVISION id={data['id']} version={data['revision']}", flush=True)
                if data["revision"] > self.vi_revisions.get(data["id"], -1):
                    self.vi_revisions[data["id"]] = data["revision"]
                    if self.preview_id == data["id"]:
                        preview = data.get("preview", "")
                        if preview:
                            self.vietnamese_live.setText(f"[{data['id']}] Bản nháp · {preview}")
                        else:
                            self.vietnamese_live.clear()
            elif kind == "vietnamese_partial" and data["id"] not in self.final_vi_ids:
                if data.get("revision", 0) < self.vi_revisions.get(data["id"], -1):
                    continue
                self.vi_revisions[data["id"]] = data.get("revision", 0)
                if self.preview_id is not None and data["id"] < self.preview_id:
                    # Suppressed because a newer segment owns the live label.
                    # Do not record as rendered.
                    continue
                self.preview_id = data["id"]
                now = time.monotonic()
                self.vietnamese_live.setText(f"[{data['id']}] Bản nháp · {data['text']}")
                self.first_vietnamese_received.setdefault(data["id"], data["latency"])
                # Record rendered timestamp only when actually displayed
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
                    self.vietnamese_live.clear()
                    self.preview_id = None
            elif kind == "vietnamese_final" and data["id"] not in self.final_vi_ids:
                self.final_vi_ids.add(data["id"])
                now = time.monotonic()
                self.final_vi.insert(0, f"[{data['id']}] {data['text']}")
                del self.final_vi[100:]
                self.show_history(self.vietnamese, self.final_vi)
                if self.preview_id == data["id"]:
                    self.vietnamese_live.clear()
                    self.preview_id = None
                # If no partial was ever rendered (e.g. fast single-word segment or suppressed),
                # the final line is its first visible Vietnamese text.
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
                self.vietnamese_live.clear()
                self.english_live.clear()
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
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    window = Window()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
