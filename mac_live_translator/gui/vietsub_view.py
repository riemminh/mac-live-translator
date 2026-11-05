"""Live Vietsub 2.0 view layout with hero subtitle card and bilingual transcript."""

from __future__ import annotations

from typing import TYPE_CHECKING
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from mac_live_translator.gui.window import Window


def create_vietsub_view(window: Window) -> QWidget:
    """Build the detailed Live Vietsub 2.0 view with hero subtitle card and history."""
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 4, 0, 0)
    layout.setSpacing(8)

    # Hero Live Subtitle Card
    vi_card = QFrame()
    vi_card.setStyleSheet("background-color: #1d1826; border: 1px solid #4a3828; border-radius: 8px;")
    vi_layout = QVBoxLayout(vi_card)
    vi_layout.setContentsMargins(12, 10, 12, 10)
    vi_layout.setSpacing(4)

    vi_top = QHBoxLayout()
    vi_badge = QLabel("VI")
    vi_badge.setStyleSheet("background-color: #ea580c; color: white; font-weight: 800; font-size: 10px; border-radius: 3px; padding: 2px 5px;")
    en_badge = QLabel("EN")
    en_badge.setStyleSheet("background-color: #6366f1; color: white; font-weight: 800; font-size: 10px; border-radius: 3px; padding: 2px 5px;")
    vi_title = QLabel("Phụ đề đang nói (Live Caption)")
    vi_title.setStyleSheet("font-size: 12px; font-weight: 600; color: #f8fafc;")
    vi_top.addWidget(vi_badge)
    vi_top.addWidget(en_badge)
    vi_top.addWidget(vi_title)
    vi_top.addStretch()
    window.vi_status_pill = QLabel("🟢 Đang lắng nghe…")
    window.vi_status_pill.setStyleSheet("color: #4ade80; font-size: 11px; font-weight: 600;")
    vi_top.addWidget(window.vi_status_pill)
    vi_layout.addLayout(vi_top)

    window.vietnamese_live = QLabel("Đang lắng nghe cuộc họp…")
    window.vietnamese_live.setWordWrap(True)
    window.vietnamese_live.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    window.vietnamese_live.setStyleSheet(
        "color: #fed7aa; font-size: 16px; font-weight: 700; line-height: 1.4; min-height: 48px;"
    )
    vi_layout.addWidget(window.vietnamese_live)

    window.english_live = QLabel("Waiting for speech…")
    window.english_live.setWordWrap(True)
    window.english_live.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    window.english_live.setStyleSheet("color: #94a3b8; font-size: 12px; line-height: 1.3; min-height: 24px;")
    vi_layout.addWidget(window.english_live)
    layout.addWidget(vi_card)

    # Recent Confirmed Captions Card
    recent_card = QFrame()
    recent_card.setStyleSheet("background-color: #1a1622; border: 1px solid #2e283b; border-radius: 8px;")
    recent_layout = QVBoxLayout(recent_card)
    recent_layout.setContentsMargins(10, 6, 10, 6)
    recent_layout.setSpacing(3)
    rec_lbl = QLabel("💬 Phụ đề vừa xác nhận (Recent Confirmed):")
    rec_lbl.setStyleSheet("font-size: 11px; font-weight: 700; color: #94a3b8;")
    recent_layout.addWidget(rec_lbl)
    window.recent_captions_label = QLabel("Chưa có phụ đề hoàn tất gần đây.")
    window.recent_captions_label.setWordWrap(True)
    window.recent_captions_label.setStyleSheet("font-size: 12px; color: #cbd5e1; font-style: italic; line-height: 1.35;")
    recent_layout.addWidget(window.recent_captions_label)
    layout.addWidget(recent_card)

    # Context chip (kept for Meeting Copilot compatibility)
    window.context_label = QLabel("Chưa có ngữ cảnh")
    window.context_label.setVisible(False)

    # Metrics Bar
    metrics_bar = QHBoxLayout()
    window.listening_badge = QLabel("🟢 Đang nghe")
    window.listening_badge.setStyleSheet("color: #4ade80; font-size: 11px; font-weight: 600;")
    metrics_bar.addWidget(window.listening_badge)
    window.draft_metric = QLabel("⏱ Nháp: —")
    window.draft_metric.setStyleSheet("color: #facc15; font-size: 11px;")
    metrics_bar.addWidget(window.draft_metric)
    window.first_token_metric = QLabel("⏱ Ổn định: —")
    window.first_token_metric.setStyleSheet("color: #38bdf8; font-size: 11px;")
    metrics_bar.addWidget(window.first_token_metric)
    window.final_metric = QLabel("⏱ Final: —")
    window.final_metric.setStyleSheet("color: #94a3b8; font-size: 11px;")
    metrics_bar.addWidget(window.final_metric)
    window.queue_metric = QLabel("📦 Hàng đợi: 0")
    window.queue_metric.setStyleSheet("color: #94a3b8; font-size: 11px;")
    metrics_bar.addWidget(window.queue_metric)
    metrics_bar.addStretch()
    window.metrics = QLabel("")
    window.metrics.setVisible(False)
    metrics_bar.addWidget(window.metrics)
    layout.addLayout(metrics_bar)

    # Transcript History Card
    hist_card = QFrame()
    hist_card.setStyleSheet("background-color: #1a1622; border: 1px solid #2e283b; border-radius: 8px;")
    hist_layout = QVBoxLayout(hist_card)
    hist_layout.setContentsMargins(10, 8, 10, 8)
    hist_layout.setSpacing(6)

    hist_top = QHBoxLayout()
    h_title = QLabel("🕒 Toàn bộ biên bản hội thoại")
    h_title.setStyleSheet("font-size: 12px; font-weight: 700; color: #ffffff;")
    hist_top.addWidget(h_title)
    hist_top.addStretch()

    btn_hist_vi = QPushButton("VI - Bản dịch")
    btn_hist_en = QPushButton("EN - Transcript")
    btn_hist_bi = QPushButton("Song ngữ (Bilingual)")
    for b in (btn_hist_vi, btn_hist_en, btn_hist_bi):
        b.setStyleSheet("background-color: #2a2538; color: #cbd5e1; padding: 2px 8px; font-size: 10px; border-radius: 4px;")
    btn_hist_vi.setStyleSheet("background-color: #ea580c; color: white; font-weight: 700; padding: 2px 8px; font-size: 10px; border-radius: 4px;")
    hist_top.addWidget(btn_hist_vi)
    hist_top.addWidget(btn_hist_en)
    hist_top.addWidget(btn_hist_bi)
    hist_layout.addLayout(hist_top)

    history_stack = QStackedWidget()
    window.vietnamese = QTextEdit()
    window.vietnamese.setReadOnly(True)
    window.english = QTextEdit()
    window.english.setReadOnly(True)
    window.bilingual = QTextEdit()
    window.bilingual.setReadOnly(True)
    history_stack.addWidget(window.vietnamese)
    history_stack.addWidget(window.english)
    history_stack.addWidget(window.bilingual)
    hist_layout.addWidget(history_stack, 1)

    def switch_tab(idx: int) -> None:
        history_stack.setCurrentIndex(idx)
        for b in (btn_hist_vi, btn_hist_en, btn_hist_bi):
            b.setStyleSheet("background-color: #2a2538; color: #cbd5e1; padding: 2px 8px; font-size: 10px; border-radius: 4px;")
        active_btn = btn_hist_vi if idx == 0 else (btn_hist_en if idx == 1 else btn_hist_bi)
        bg = "#ea580c" if idx == 0 else ("#6366f1" if idx == 1 else "#059669")
        active_btn.setStyleSheet(f"background-color: {bg}; color: white; font-weight: 700; padding: 2px 8px; font-size: 10px; border-radius: 4px;")

    btn_hist_vi.clicked.connect(lambda: switch_tab(0))
    btn_hist_en.clicked.connect(lambda: switch_tab(1))
    btn_hist_bi.clicked.connect(lambda: switch_tab(2))
    layout.addWidget(hist_card, 1)

    return container

