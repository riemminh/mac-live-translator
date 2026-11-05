"""Unified left workspace panel hosting Understanding Mode and Live Vietsub 2.0."""

from __future__ import annotations

from typing import TYPE_CHECKING
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from mac_live_translator.gui.understanding_panel import create_understanding_panel
from mac_live_translator.gui.vietsub_view import create_vietsub_view

if TYPE_CHECKING:
    from mac_live_translator.gui.window import Window


def create_translation_panel(window: Window) -> QWidget:
    """Build the left workspace panel supporting Visual Understanding and Live Vietsub modes."""
    panel = QFrame()
    panel.setProperty("class", "cardFrame")
    panel.setStyleSheet("QFrame.cardFrame { background-color: #211c2b; border: 1px solid #342e42; border-radius: 12px; }")
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(8)

    # Top Header with Mode Switcher
    head_row = QHBoxLayout()
    title_box = QVBoxLayout()
    title_box.setSpacing(2)
    t_lbl = QLabel("Phụ đề & Hiểu cuộc họp")
    t_lbl.setStyleSheet("font-size: 15px; font-weight: 700; color: #ffffff;")
    s_lbl = QLabel("Visual Meeting Understanding & Real-time Live Vietsub")
    s_lbl.setStyleSheet("font-size: 11px; color: #94a3b8;")
    title_box.addWidget(t_lbl)
    title_box.addWidget(s_lbl)
    head_row.addLayout(title_box)
    head_row.addStretch()

    # Segmented Mode Switcher
    mode_box = QHBoxLayout()
    mode_box.setSpacing(4)
    btn_mode_understand = QPushButton("🧠 Hiểu trực quan")
    btn_mode_vietsub = QPushButton("💬 Phụ đề chi tiết")
    for b in (btn_mode_understand, btn_mode_vietsub):
        b.setStyleSheet("background-color: #2a2538; color: #cbd5e1; padding: 4px 10px; font-size: 11px; font-weight: 600; border-radius: 6px;")
    btn_mode_understand.setStyleSheet("background-color: #4f46e5; color: white; padding: 4px 10px; font-size: 11px; font-weight: 700; border-radius: 6px;")
    mode_box.addWidget(btn_mode_understand)
    mode_box.addWidget(btn_mode_vietsub)
    head_row.addLayout(mode_box)
    layout.addLayout(head_row)

    # Stacked View: Page 0 = Visual Understanding, Page 1 = Live Vietsub 2.0
    stack = QStackedWidget()
    understanding_view = create_understanding_panel(window)
    vietsub_view = create_vietsub_view(window)
    stack.addWidget(understanding_view)
    stack.addWidget(vietsub_view)
    layout.addWidget(stack, 1)

    def switch_mode(idx: int) -> None:
        stack.setCurrentIndex(idx)
        btn_mode_understand.setStyleSheet("background-color: #2a2538; color: #cbd5e1; padding: 4px 10px; font-size: 11px; font-weight: 600; border-radius: 6px;")
        btn_mode_vietsub.setStyleSheet("background-color: #2a2538; color: #cbd5e1; padding: 4px 10px; font-size: 11px; font-weight: 600; border-radius: 6px;")
        active_btn = btn_mode_understand if idx == 0 else btn_mode_vietsub
        bg = "#4f46e5" if idx == 0 else "#ea580c"
        active_btn.setStyleSheet(f"background-color: {bg}; color: white; padding: 4px 10px; font-size: 11px; font-weight: 700; border-radius: 6px;")

    btn_mode_understand.clicked.connect(lambda: switch_mode(0))
    btn_mode_vietsub.clicked.connect(lambda: switch_mode(1))

    return panel
