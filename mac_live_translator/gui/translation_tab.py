"""Translation tab UI builder: device selectors, Live Focus card, and history views."""

from __future__ import annotations

from typing import TYPE_CHECKING
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from mac_live_translator.audio.devices import devices

if TYPE_CHECKING:
    from mac_live_translator.gui.window import Window


def create_translation_tab(window: Window) -> QWidget:
    """Build and bind all controls and view cards for the Live Translation tab."""
    tab = QWidget()
    layout = QVBoxLayout(tab)
    layout.setContentsMargins(10, 8, 10, 8)
    layout.setSpacing(6)

    # Device selection row
    row = QHBoxLayout()
    window.input = QComboBox()
    window.input.setMinimumWidth(240)
    window.output = QComboBox()
    window.output.setMinimumWidth(240)
    for i, dev in enumerate(devices()):
        if dev["max_input_channels"] and "blackhole 2ch" in dev["name"].casefold():
            window.input.addItem(f"{i}: {dev['name']}", i)
        if dev["max_output_channels"] and not any(
            x in dev["name"].casefold()
            for x in ("blackhole", "multi-output", "aggregate", "loopback")
        ):
            window.output.addItem(f"{i}: {dev['name']}", i)
    row.addWidget(QLabel("Capture:"))
    row.addWidget(window.input)
    row.addWidget(QLabel("Headphones:"))
    row.addWidget(window.output)
    layout.addLayout(row)

    window.status = QLabel("Stopped — set macOS Output to a Multi-Output Device containing BlackHole and headphones")
    window.status.setStyleSheet("color: #555; font-size: 11px;")
    layout.addWidget(window.status)

    window.metrics = QLabel("Audio → first EN: —  ·  first VI: —  ·  final VI: —")
    window.metrics.setStyleSheet("color: #333; font-size: 11px; font-weight: 500;")
    layout.addWidget(window.metrics)

    # Meeting Follow Live Focus Container
    focus_box = QFrame()
    focus_box.setFrameShape(QFrame.Shape.StyledPanel)
    focus_box.setStyleSheet(
        "QFrame { background-color: #f8fafc; border: 1px solid #cbd5e1; border-radius: 8px; }"
    )
    focus_layout = QVBoxLayout(focus_box)
    focus_layout.setContentsMargins(12, 8, 12, 10)
    focus_layout.setSpacing(4)

    window.context_label = QLabel("Ngữ cảnh gần nhất: —")
    window.context_label.setWordWrap(True)
    window.context_label.setStyleSheet("color: #64748b; font-size: 11px; font-style: italic;")
    focus_layout.addWidget(window.context_label)

    window.vietnamese_live = QLabel("Chưa có bản dịch trực tiếp")
    window.vietnamese_live.setWordWrap(True)
    window.vietnamese_live.setStyleSheet(
        "color: #0369a1; font-size: 17px; font-weight: 700; min-height: 40px; line-height: 1.3;"
    )
    focus_layout.addWidget(window.vietnamese_live)

    window.english_live = QLabel("Waiting for speech…")
    window.english_live.setWordWrap(True)
    window.english_live.setStyleSheet("color: #334155; font-size: 12px;")
    focus_layout.addWidget(window.english_live)
    layout.addWidget(focus_box)

    # Subtitle history
    layout.addWidget(QLabel("Lịch sử bản dịch tiếng Việt (Vietnamese History)"))
    window.vietnamese = QTextEdit()
    window.vietnamese.setReadOnly(True)
    layout.addWidget(window.vietnamese, 1)

    layout.addWidget(QLabel("Biên bản tiếng Anh gốc (English Transcript)"))
    window.english = QTextEdit()
    window.english.setReadOnly(True)
    layout.addWidget(window.english, 1)

    # Bottom controls
    controls = QHBoxLayout()
    window.start_button = QPushButton("Start Meeting Follow")
    window.stop_button = QPushButton("Stop")
    window.stop_button.setEnabled(False)
    window.top = QCheckBox("Always on top")
    window.top.toggled.connect(window.toggle_top)
    window.start_button.clicked.connect(window.start)
    window.stop_button.clicked.connect(window.stop)
    controls.addWidget(window.start_button)
    controls.addWidget(window.stop_button)
    controls.addWidget(window.top)
    layout.addLayout(controls)

    return tab

