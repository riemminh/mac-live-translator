"""Meeting Copilot workspace panel with quick actions, streaming hero reply, and sources."""

from __future__ import annotations

from typing import TYPE_CHECKING
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from mac_live_translator.gui.window import Window


def create_copilot_panel(window: Window) -> QWidget:
    """Build the right Meeting Copilot panel matching the native macOS mockup."""
    panel = QFrame()
    panel.setProperty("class", "cardFrame")
    panel.setStyleSheet("QFrame.cardFrame { background-color: #211c2b; border: 1px solid #342e42; border-radius: 12px; }")
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(8)

    # Header
    title_box = QVBoxLayout()
    title_box.setSpacing(2)
    t_lbl = QLabel("🤖 Copilot hỗ trợ cuộc họp")
    t_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: #ffffff;")
    s_lbl = QLabel("Meeting Copilot · Soạn phản hồi, giải thích ngữ cảnh, gợi ý câu hỏi")
    s_lbl.setStyleSheet("font-size: 11px; color: #94a3b8;")
    title_box.addWidget(t_lbl)
    title_box.addWidget(s_lbl)
    layout.addLayout(title_box)

    # Cloud Opt-in & Model Bar
    opt_box = QFrame()
    opt_box.setStyleSheet("background-color: #1a1622; border: 1px solid #2e283b; border-radius: 6px;")
    opt_layout = QHBoxLayout(opt_box)
    opt_layout.setContentsMargins(10, 5, 10, 5)
    window.cloud_opt_in = QCheckBox("Sử dụng Claude AI (Cloud Assistance Opt-In)")
    window.cloud_opt_in.setStyleSheet("font-weight: 600; color: #f1f5f9; font-size: 11px;")
    window.cloud_opt_in.setChecked(False)
    opt_layout.addWidget(window.cloud_opt_in)
    opt_layout.addStretch()

    window.model_combo = QComboBox()
    window.model_combo.addItems(["claude-haiku-5-5", "claude-3-5-haiku-20241022"])
    opt_layout.addWidget(window.model_combo)

    btn_settings = QPushButton("⚙ Key")
    btn_settings.setStyleSheet("padding: 2px 8px; font-size: 10px;")
    btn_settings.clicked.connect(window.copilot_actions.open_settings_dialog)
    opt_layout.addWidget(btn_settings)
    layout.addWidget(opt_box)

    # Knowledge & Context Dual Summary Chips
    store_row = QHBoxLayout()
    k_card = QFrame()
    k_card.setCursor(Qt.CursorShape.PointingHandCursor)
    k_card.setStyleSheet("QFrame { background-color: #1a1622; border: 1px solid #2e283b; border-radius: 8px; } QFrame:hover { border-color: #7c3aed; }")
    k_layout = QVBoxLayout(k_card)
    k_layout.setContentsMargins(10, 6, 10, 6)
    k_layout.setSpacing(2)
    k_top = QHBoxLayout()
    k_top.addWidget(QLabel("📄 Tài liệu (.md, .txt)"))
    window.knowledge_badge = QLabel("0 tệp")
    window.knowledge_badge.setStyleSheet("background-color: #581c87; color: #e9d5ff; font-size: 10px; font-weight: 700; border-radius: 4px; padding: 1px 6px;")
    k_top.addWidget(window.knowledge_badge)
    k_layout.addLayout(k_top)
    window.knowledge_status = QLabel("Quản lý tệp tri thức >")
    window.knowledge_status.setStyleSheet("font-size: 10px; color: #94a3b8;")
    k_layout.addWidget(window.knowledge_status)
    k_card.mousePressEvent = lambda _: window.copilot_actions.open_knowledge_dialog()
    store_row.addWidget(k_card)

    c_card = QFrame()
    c_card.setCursor(Qt.CursorShape.PointingHandCursor)
    c_card.setStyleSheet("QFrame { background-color: #1a1622; border: 1px solid #2e283b; border-radius: 8px; } QFrame:hover { border-color: #10b981; }")
    c_layout = QVBoxLayout(c_card)
    c_layout.setContentsMargins(10, 6, 10, 6)
    c_layout.setSpacing(2)
    c_top = QHBoxLayout()
    c_top.addWidget(QLabel("📚 Ngữ cảnh họp"))
    window.context_badge = QLabel("0 câu / 0 từ")
    window.context_badge.setStyleSheet("background-color: #064e3b; color: #a7f3d0; font-size: 10px; font-weight: 700; border-radius: 4px; padding: 1px 6px;")
    c_top.addWidget(window.context_badge)
    c_layout.addLayout(c_top)
    window.context_status = QLabel("Biên bản cuộc họp hiện tại >")
    window.context_status.setStyleSheet("font-size: 10px; color: #94a3b8;")
    c_layout.addWidget(window.context_status)
    c_card.mousePressEvent = lambda _: window.copilot_actions.review_context_snapshot()
    store_row.addWidget(c_card)
    layout.addLayout(store_row)

    # Question Input
    q_lbl = QLabel("✏️ Câu hỏi hoặc yêu cầu cụ thể (để Copilot hỗ trợ tốt nhất)...")
    q_lbl.setStyleSheet("font-size: 11px; font-weight: 600; color: #94a3b8;")
    layout.addWidget(q_lbl)
    window.question_input = QLineEdit()
    window.question_input.setPlaceholderText("Bạn muốn trả lời hoặc hỏi điều gì trong cuộc họp?")
    layout.addWidget(window.question_input)

    # Action Buttons
    act_row = QHBoxLayout()
    window.btn_help_reply = QPushButton("💬 Help Me Reply\nGợi ý câu trả lời")
    window.btn_help_reply.setObjectName("primaryCopilotBtn")
    window.btn_help_reply.setCursor(Qt.CursorShape.PointingHandCursor)
    act_row.addWidget(window.btn_help_reply, 2)

    window.btn_explain = QPushButton("🔍 Explain Context\nGiải thích ngữ cảnh")
    window.btn_explain.setCursor(Qt.CursorShape.PointingHandCursor)
    act_row.addWidget(window.btn_explain, 1)

    window.btn_suggest = QPushButton("❓ Suggest Question\nGợi ý câu hỏi")
    window.btn_suggest.setCursor(Qt.CursorShape.PointingHandCursor)
    act_row.addWidget(window.btn_suggest, 1)

    window.btn_cancel_copilot = QPushButton("✖ Hủy")
    window.btn_cancel_copilot.setEnabled(False)
    act_row.addWidget(window.btn_cancel_copilot)
    layout.addLayout(act_row)

    # Suggested English Reply (Hero Output)
    ans_box = QFrame()
    ans_box.setStyleSheet("background-color: #1a1622; border: 1px solid #4a3b69; border-radius: 8px;")
    ans_layout = QVBoxLayout(ans_box)
    ans_layout.setContentsMargins(10, 8, 10, 8)
    ans_top = QHBoxLayout()
    ans_top.addWidget(QLabel("📅 Gợi ý phản hồi (tiếng Anh) · Suggested Reply"))
    ans_top.addStretch()
    window.btn_copy_english = QPushButton("📋 Sao chép")
    window.btn_copy_english.setStyleSheet("padding: 2px 8px; font-size: 10px;")
    ans_top.addWidget(window.btn_copy_english)
    ans_layout.addLayout(ans_top)
    window.english_answer_view = QTextEdit()
    window.english_answer_view.setReadOnly(True)
    window.english_answer_view.setStyleSheet("font-size: 14px; font-weight: 600; color: #ffffff; min-height: 55px;")
    ans_layout.addWidget(window.english_answer_view)
    layout.addWidget(ans_box, 1)

    # Vietnamese Meaning & Evidence Side-by-Side
    out_row = QHBoxLayout()
    vi_box = QFrame()
    vi_box.setStyleSheet("background-color: #1a1622; border: 1px solid #2e283b; border-radius: 8px;")
    vi_l = QVBoxLayout(vi_box)
    vi_l.setContentsMargins(8, 6, 8, 6)
    vi_l.addWidget(QLabel("文A Ý nghĩa / Bản dịch tiếng Việt"))
    window.vietnamese_meaning_view = QTextEdit()
    window.vietnamese_meaning_view.setReadOnly(True)
    window.vietnamese_meaning_view.setStyleSheet("color: #cbd5e1; font-size: 11px;")
    vi_l.addWidget(window.vietnamese_meaning_view)
    out_row.addWidget(vi_box, 1)

    ev_box = QFrame()
    ev_box.setStyleSheet("background-color: #1a1622; border: 1px solid #2e283b; border-radius: 8px;")
    ev_l = QVBoxLayout(ev_box)
    ev_l.setContentsMargins(8, 6, 8, 6)
    ev_l.addWidget(QLabel("📚 Căn cứ / Nguồn tham chiếu (Evidence)"))
    window.evidence_view = QTextEdit()
    window.evidence_view.setReadOnly(True)
    window.evidence_view.setStyleSheet("color: #a1a1aa; font-size: 11px;")
    ev_l.addWidget(window.evidence_view)
    out_row.addWidget(ev_box, 1)
    layout.addLayout(out_row, 1)

    # Context Preview Banner
    btn_prev = QPushButton("ℹ️ Ngữ cảnh sẽ gửi cho AI (xem trước) · Bấm để xem chi tiết prompt và trích đoạn ↗")
    btn_prev.setStyleSheet("background-color: #1a1622; border: 1px solid #2e283b; color: #94a3b8; font-size: 11px; padding: 4px;")
    btn_prev.clicked.connect(window.copilot_actions.review_context_snapshot)
    layout.addWidget(btn_prev)

    # Copilot Metrics Bar
    window.copilot_metrics = QLabel("Copilot: Sẵn sàng · Latency: — · Tokens: —")
    window.copilot_metrics.setStyleSheet("color: #64748b; font-size: 11px;")
    layout.addWidget(window.copilot_metrics)

    return panel
