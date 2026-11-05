"""PySide6 layout for the Visual Meeting Understanding mode."""

from __future__ import annotations

from typing import TYPE_CHECKING
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from mac_live_translator.gui.window import Window


def create_understanding_panel(window: Window) -> QWidget:
    """Build the Visual Meeting Understanding mode panel."""
    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 4, 0, 0)
    layout.setSpacing(6)

    # Cloud Opt-in & Privacy Bar
    opt_card = QFrame()
    opt_card.setStyleSheet("background-color: #1a1622; border: 1px solid #2e283b; border-radius: 6px;")
    opt_layout = QHBoxLayout(opt_card)
    opt_layout.setContentsMargins(8, 4, 8, 4)

    window.understanding_opt_in = QCheckBox("☁️ Bật phân tích hiểu cuộc họp (Cloud Understanding Opt-In)")
    window.understanding_opt_in.setChecked(False)
    window.understanding_opt_in.setStyleSheet("color: #f1f5f9; font-size: 11px; font-weight: 600;")
    opt_layout.addWidget(window.understanding_opt_in)
    opt_layout.addStretch()

    window.understanding_status_lbl = QLabel("⚪ Ngoại tuyến (Offline)")
    window.understanding_status_lbl.setStyleSheet("color: #94a3b8; font-size: 10px;")
    opt_layout.addWidget(window.understanding_status_lbl)
    layout.addWidget(opt_card)

    # Topic Card
    topic_card = QFrame()
    topic_card.setStyleSheet("background-color: #1a1622; border: 1px solid #342e42; border-radius: 8px;")
    t_layout = QHBoxLayout(topic_card)
    t_layout.setContentsMargins(10, 6, 10, 6)
    t_lbl_prefix = QLabel("📌 Chủ đề:")
    t_lbl_prefix.setStyleSheet("color: #a78bfa; font-weight: 700; font-size: 11px;")
    t_layout.addWidget(t_lbl_prefix)
    window.topic_label = QLabel("Đang lắng nghe để xác định chủ đề…")
    window.topic_label.setStyleSheet("color: #ffffff; font-weight: 700; font-size: 12px;")
    window.topic_label.setWordWrap(True)
    t_layout.addWidget(window.topic_label, 1)
    layout.addWidget(topic_card)

    # Pinned Question Banner (hidden by default)
    window.pinned_question_card = QFrame()
    window.pinned_question_card.setStyleSheet("background-color: #0c2a44; border: 1px solid #0284c7; border-radius: 6px;")
    q_layout = QHBoxLayout(window.pinned_question_card)
    q_layout.setContentsMargins(10, 6, 10, 6)
    q_prefix = QLabel("❓ Đang thảo luận:")
    q_prefix.setStyleSheet("color: #38bdf8; font-weight: 700; font-size: 11px;")
    q_layout.addWidget(q_prefix)
    window.pinned_question_label = QLabel("")
    window.pinned_question_label.setStyleSheet("color: #e0f2fe; font-size: 12px; font-weight: 600;")
    window.pinned_question_label.setWordWrap(True)
    q_layout.addWidget(window.pinned_question_label, 1)
    window.pinned_question_card.setVisible(False)
    layout.addWidget(window.pinned_question_card)

    # Freeze & Catch Up Toolbar
    ctrl_bar = QHBoxLayout()
    ctrl_bar.setSpacing(6)
    window.freeze_checkbox = QCheckBox("⏸ Tạm dừng cuộn (Freeze Reading)")
    window.freeze_checkbox.setStyleSheet("color: #f1f5f9; font-size: 11px; font-weight: 600;")
    ctrl_bar.addWidget(window.freeze_checkbox)

    window.backlog_badge = QLabel("🔔 0 ý mới")
    window.backlog_badge.setStyleSheet("background-color: #27272a; color: #a1a1aa; font-size: 10px; font-weight: 700; border-radius: 4px; padding: 2px 6px;")
    ctrl_bar.addWidget(window.backlog_badge)
    ctrl_bar.addStretch()

    window.btn_catchup = QPushButton("⚡ Bắt kịp (Catch Up)")
    window.btn_catchup.setStyleSheet("background-color: #3b82f6; color: white; font-weight: 700; font-size: 10px; padding: 3px 8px; border-radius: 4px;")
    window.btn_catchup.setEnabled(False)
    ctrl_bar.addWidget(window.btn_catchup)
    layout.addLayout(ctrl_bar)

    # Catchup Recap Notice Banner (hidden by default)
    window.catchup_banner = QLabel("")
    window.catchup_banner.setWordWrap(True)
    window.catchup_banner.setStyleSheet("background-color: #1e1b4b; border: 1px solid #4338ca; color: #c7d2fe; font-size: 11px; padding: 4px 8px; border-radius: 4px;")
    window.catchup_banner.setVisible(False)
    layout.addWidget(window.catchup_banner)

    # Meaning Cards Scroll Area
    cards_scroll = QScrollArea()
    cards_scroll.setWidgetResizable(True)
    cards_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
    window.cards_container = QWidget()
    window.cards_container.setStyleSheet("background: transparent;")
    window.cards_layout = QVBoxLayout(window.cards_container)
    window.cards_layout.setContentsMargins(0, 0, 0, 0)
    window.cards_layout.setSpacing(6)
    window.cards_layout.addStretch()
    cards_scroll.setWidget(window.cards_container)
    layout.addWidget(cards_scroll, 2)

    # Confirmed Decisions & Actions Section
    window.decisions_card = QFrame()
    window.decisions_card.setStyleSheet("background-color: #17131e; border: 1px solid #2e283b; border-radius: 6px;")
    dec_layout = QVBoxLayout(window.decisions_card)
    dec_layout.setContentsMargins(8, 6, 8, 6)
    dec_layout.setSpacing(4)
    dec_top = QHBoxLayout()
    dec_title = QLabel("📌 Quyết định & Hành động đã chốt")
    dec_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #a1a1aa;")
    dec_top.addWidget(dec_title)
    dec_top.addStretch()
    dec_layout.addLayout(dec_top)
    window.decisions_container = QVBoxLayout()
    window.decisions_container.setSpacing(3)
    dec_layout.addLayout(window.decisions_container)
    layout.addWidget(window.decisions_card, 1)

    # Compact Live Vietnamese Subtitle (Reference)
    compact_sub = QFrame()
    compact_sub.setStyleSheet("background-color: #17131e; border: 1px solid #342e42; border-radius: 6px;")
    sub_layout = QVBoxLayout(compact_sub)
    sub_layout.setContentsMargins(8, 6, 8, 6)
    sub_layout.setSpacing(2)
    sub_top = QHBoxLayout()
    sub_badge = QLabel("VI PHỤ ĐỀ TRỰC TIẾP")
    sub_badge.setStyleSheet("background-color: #ea580c; color: white; font-size: 9px; font-weight: 700; border-radius: 2px; padding: 1px 4px;")
    sub_top.addWidget(sub_badge)
    sub_top.addStretch()
    sub_layout.addLayout(sub_top)
    window.compact_vi_live = QLabel("Đang lắng nghe cuộc họp…")
    window.compact_vi_live.setWordWrap(True)
    window.compact_vi_live.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    window.compact_vi_live.setStyleSheet("color: #fed7aa; font-size: 13px; font-weight: 700; line-height: 1.25;")
    sub_layout.addWidget(window.compact_vi_live)
    layout.addWidget(compact_sub)

    return panel

