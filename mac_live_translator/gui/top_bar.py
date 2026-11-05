"""Top control bar for audio device routing, session controls, and latency indicators."""

from __future__ import annotations

from typing import TYPE_CHECKING
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mac_live_translator.audio.devices import devices

if TYPE_CHECKING:
    from mac_live_translator.gui.window import Window


def create_top_bar(window: Window) -> QWidget:
    """Build the compact top persistent control bar matching the native macOS mockup."""
    bar = QFrame()
    bar.setProperty("class", "cardFrame")
    bar.setStyleSheet("QFrame.cardFrame { background-color: #1e1a27; border: 1px solid #352e44; border-radius: 10px; }")
    layout = QHBoxLayout(bar)
    layout.setContentsMargins(12, 8, 12, 8)
    layout.setSpacing(10)

    # Audio Waveform Icon indicator
    wave_lbl = QLabel("🎙️")
    wave_lbl.setStyleSheet("font-size: 18px;")
    layout.addWidget(wave_lbl)

    # Capture Device
    cap_box = QVBoxLayout()
    cap_box.setSpacing(2)
    cap_lbl = QLabel("Thiết bị thu (Capture)")
    cap_lbl.setProperty("class", "fieldLabel")
    cap_box.addWidget(cap_lbl)
    window.input = QComboBox()
    window.input.setMinimumWidth(180)
    cap_box.addWidget(window.input)
    layout.addLayout(cap_box)

    # Headphone Output Device
    head_box = QVBoxLayout()
    head_box.setSpacing(2)
    head_lbl = QLabel("Tai nghe (Headphones)")
    head_lbl.setProperty("class", "fieldLabel")
    head_box.addWidget(head_lbl)
    window.output = QComboBox()
    window.output.setMinimumWidth(180)
    head_box.addWidget(window.output)
    layout.addLayout(head_box)

    # Populate devices safely
    for i, dev in enumerate(devices()):
        if dev["max_input_channels"] and "blackhole 2ch" in dev["name"].casefold():
            window.input.addItem(f"{i}: {dev['name']}", i)
        if dev["max_output_channels"] and not any(
            x in dev["name"].casefold()
            for x in ("blackhole", "multi-output", "aggregate", "loopback")
        ):
            window.output.addItem(f"{i}: {dev['name']}", i)

    # Start and Stop Buttons
    window.start_button = QPushButton("▶ Bắt đầu (Start)")
    window.start_button.setObjectName("startBtn")
    window.start_button.setCursor(Qt.CursorShape.PointingHandCursor)
    window.start_button.clicked.connect(window.start)
    layout.addWidget(window.start_button)

    window.stop_button = QPushButton("⏹ Dừng (Stop)")
    window.stop_button.setObjectName("stopBtn")
    window.stop_button.setCursor(Qt.CursorShape.PointingHandCursor)
    window.stop_button.setEnabled(False)
    window.stop_button.clicked.connect(window.stop)
    layout.addWidget(window.stop_button)

    # Always On Top Switch
    top_box = QVBoxLayout()
    top_box.setSpacing(2)
    window.top_check = QCheckBox("Luôn nổi trên cùng\nAlways on top")
    window.top_check.setStyleSheet("font-size: 11px; color: #cbd5e1;")
    window.top_check.toggled.connect(window.toggle_top)
    top_box.addWidget(window.top_check)
    layout.addLayout(top_box)

    layout.addStretch()

    # Cloud AI Status Badge
    window.ai_status_pill = QLabel("🟢 AI sẵn sàng\nClaude (Cloud)")
    window.ai_status_pill.setStyleSheet(
        "background-color: #143525; border: 1px solid #166534; border-radius: 6px; "
        "color: #4ade80; font-size: 11px; font-weight: 600; padding: 4px 10px;"
    )
    layout.addWidget(window.ai_status_pill)

    # Latency Metric Pill
    window.latency_pill = QLabel("⚡ Độ trễ: —")
    window.latency_pill.setStyleSheet(
        "background-color: #2a2015; border: 1px solid #78350f; border-radius: 6px; "
        "color: #fbbf24; font-size: 11px; font-weight: 600; padding: 4px 10px;"
    )
    layout.addWidget(window.latency_pill)

    # Hidden status label for pipeline messages
    window.status = QLabel("Stopped")
    window.status.setVisible(False)
    layout.addWidget(window.status)

    return bar

