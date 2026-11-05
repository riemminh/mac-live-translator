"""Live translation workspace panel with real-time subtitles and history stack."""

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


def create_translation_panel(window: Window) -> QWidget:
    """Build the left live translation panel matching the native macOS mockup."""
    panel = QFrame()
    panel.setProperty("class", "cardFrame")
    panel.setStyleSheet("QFrame.cardFrame { background-color: #211c2b; border: 1px solid #342e42; border-radius: 12px; }")
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(10)

    # Header Row
    head_row = QHBoxLayout()
    title_box = QVBoxLayout()
    title_box.setSpacing(2)
    t_lbl = QLabel("Theo dõi cuộc họp trực tiếp")
    t_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: #ffffff;")
    s_lbl = QLabel("Live Meeting Follow · Dịch thời gian thực & biên bản")
    s_lbl.setStyleSheet("font-size: 11px; color: #94a3b8;")
    title_box.addWidget(t_lbl)
    title_box.addWidget(s_lbl)
    head_row.addLayout(title_box)
    head_row.addStretch()
    layout.addLayout(head_row)

    # Recent Context Chip
    ctx_chip = QFrame()
    ctx_chip.setStyleSheet("background-color: #1a1622; border: 1px solid #2e283b; border-radius: 6px;")
    ctx_layout = QHBoxLayout(ctx_chip)
    ctx_layout.setContentsMargins(8, 4, 8, 4)
    ctx_tag = QLabel("📄 Ngữ cảnh gần nhất:")
    ctx_tag.setStyleSheet("font-size: 11px; font-weight: 600; color: #94a3b8;")
    window.context_label = QLabel("Chưa có ngữ cảnh")
    window.context_label.setStyleSheet("font-size: 11px; color: #e2e8f0; font-style: italic;")
    window.context_label.setWordWrap(True)
    ctx_layout.addWidget(ctx_tag)
    ctx_layout.addWidget(window.context_label, 1)
    layout.addWidget(ctx_chip)

    # Hero Live Vietnamese Translation Card
    vi_card = QFrame()
    vi_card.setStyleSheet("background-color: #1d1826; border: 1px solid #4a3828; border-radius: 8px;")
    vi_layout = QVBoxLayout(vi_card)
    vi_layout.setContentsMargins(12, 10, 12, 12)
    vi_layout.setSpacing(6)

    vi_top = QHBoxLayout()
    vi_badge = QLabel("VI")
    vi_badge.setStyleSheet("background-color: #ea580c; color: white; font-weight: 800; font-size: 10px; border-radius: 3px; padding: 2px 5px;")
    vi_title = QLabel("Bản dịch tiếng Việt (trực tiếp)")
    vi_title.setStyleSheet("font-size: 12px; font-weight: 600; color: #f8fafc;")
    vi_top.addWidget(vi_badge)
    vi_top.addWidget(vi_title)
    vi_top.addStretch()
    window.vi_status_pill = QLabel("🟢 Đang lắng nghe…")
    window.vi_status_pill.setStyleSheet("color: #4ade80; font-size: 11px; font-weight: 500;")
    vi_top.addWidget(window.vi_status_pill)
    vi_layout.addLayout(vi_top)

    window.vietnamese_live = QLabel("Đang lắng nghe cuộc họp…")
    window.vietnamese_live.setWordWrap(True)
    window.vietnamese_live.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    window.vietnamese_live.setStyleSheet(
        "color: #fed7aa; font-size: 15px; font-weight: 600; line-height: 1.45; min-height: 64px;"
    )
    vi_layout.addWidget(window.vietnamese_live)
    layout.addWidget(vi_card)

    # Live English Transcript Card
    en_card = QFrame()
    en_card.setStyleSheet("background-color: #1a1622; border: 1px solid #2e283b; border-radius: 8px;")
    en_layout = QVBoxLayout(en_card)
    en_layout.setContentsMargins(12, 8, 12, 10)
    en_layout.setSpacing(4)

    en_top = QHBoxLayout()
    en_badge = QLabel("EN")
    en_badge.setStyleSheet("background-color: #6366f1; color: white; font-weight: 800; font-size: 10px; border-radius: 3px; padding: 2px 5px;")
    en_title = QLabel("Biên bản tiếng Anh (trực tiếp) · English Transcript (Live)")
    en_title.setStyleSheet("font-size: 12px; font-weight: 600; color: #cbd5e1;")
    en_top.addWidget(en_badge)
    en_top.addWidget(en_title)
    en_top.addStretch()
    en_layout.addLayout(en_top)

    window.english_live = QLabel("Waiting for speech…")
    window.english_live.setWordWrap(True)
    window.english_live.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    window.english_live.setStyleSheet("color: #e2e8f0; font-size: 13px; line-height: 1.35; min-height: 38px;")
    en_layout.addWidget(window.english_live)
    layout.addWidget(en_card)

    # Live Metrics Strip
    metrics_bar = QHBoxLayout()
    window.listening_badge = QLabel("🟢 Đang nghe (Listening)")
    window.listening_badge.setStyleSheet("color: #4ade80; font-size: 11px; font-weight: 600;")
    metrics_bar.addWidget(window.listening_badge)

    window.first_token_metric = QLabel("⏱ First: —")
    window.first_token_metric.setStyleSheet("color: #94a3b8; font-size: 11px;")
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

    # Transcript History Card with Stacked View Toggle
    hist_card = QFrame()
    hist_card.setStyleSheet("background-color: #1a1622; border: 1px solid #2e283b; border-radius: 8px;")
    hist_layout = QVBoxLayout(hist_card)
    hist_layout.setContentsMargins(10, 8, 10, 8)
    hist_layout.setSpacing(6)

    hist_top = QHBoxLayout()
    h_title = QLabel("🕒 Lịch sử hội thoại (gần nhất)")
    h_title.setStyleSheet("font-size: 12px; font-weight: 700; color: #ffffff;")
    hist_top.addWidget(h_title)
    hist_top.addStretch()

    btn_hist_vi = QPushButton("VI - Bản dịch")
    btn_hist_en = QPushButton("EN - Transcript")
    btn_hist_vi.setStyleSheet("background-color: #ea580c; color: white; font-weight: 700; padding: 2px 8px; font-size: 10px;")
    btn_hist_en.setStyleSheet("background-color: #2a2538; color: #cbd5e1; padding: 2px 8px; font-size: 10px;")
    hist_top.addWidget(btn_hist_vi)
    hist_top.addWidget(btn_hist_en)
    hist_layout.addLayout(hist_top)

    history_stack = QStackedWidget()
    window.vietnamese = QTextEdit()
    window.vietnamese.setReadOnly(True)
    window.english = QTextEdit()
    window.english.setReadOnly(True)
    history_stack.addWidget(window.vietnamese)
    history_stack.addWidget(window.english)
    hist_layout.addWidget(history_stack, 1)

    def switch_to_vi() -> None:
        history_stack.setCurrentIndex(0)
        btn_hist_vi.setStyleSheet("background-color: #ea580c; color: white; font-weight: 700; padding: 2px 8px; font-size: 10px;")
        btn_hist_en.setStyleSheet("background-color: #2a2538; color: #cbd5e1; padding: 2px 8px; font-size: 10px;")

    def switch_to_en() -> None:
        history_stack.setCurrentIndex(1)
        btn_hist_en.setStyleSheet("background-color: #6366f1; color: white; font-weight: 700; padding: 2px 8px; font-size: 10px;")
        btn_hist_vi.setStyleSheet("background-color: #2a2538; color: #cbd5e1; padding: 2px 8px; font-size: 10px;")

    btn_hist_vi.clicked.connect(switch_to_vi)
    btn_hist_en.clicked.connect(switch_to_en)
    layout.addWidget(hist_card, 1)

    return panel
