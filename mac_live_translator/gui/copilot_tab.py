"""Copilot tab UI builder: privacy authorization, knowledge panels, and reply hero card."""

from __future__ import annotations

from typing import TYPE_CHECKING
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


def create_copilot_tab(window: Window) -> QWidget:
    """Build and bind all controls and cards for the Meeting Copilot tab."""
    tab = QWidget()
    layout = QVBoxLayout(tab)
    layout.setContentsMargins(10, 8, 10, 8)
    layout.setSpacing(8)

    # Card 1: Cloud Privacy & API Authorization
    auth_box = QFrame()
    auth_box.setStyleSheet("QFrame { background-color: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 6px; }")
    auth_layout = QVBoxLayout(auth_box)
    auth_layout.setContentsMargins(10, 6, 10, 6)
    auth_layout.setSpacing(4)

    top_auth_row = QHBoxLayout()
    window.cloud_opt_in = QCheckBox("Cho phép sử dụng Claude AI (Cloud Assistance Opt-In)")
    window.cloud_opt_in.setStyleSheet("font-weight: bold; color: #0f172a;")
    window.cloud_opt_in.setChecked(False)
    window.cloud_opt_in.toggled.connect(window.copilot_actions.on_opt_in_toggled)
    top_auth_row.addWidget(window.cloud_opt_in)

    top_auth_row.addSpacing(15)
    top_auth_row.addWidget(QLabel("Model:"))
    window.model_combo = QComboBox()
    window.model_combo.addItems(["claude-haiku-5-5", "claude-3-5-haiku-20241022"])
    window.model_combo.currentTextChanged.connect(window.copilot_actions.on_model_changed)
    top_auth_row.addWidget(window.model_combo)
    auth_layout.addLayout(top_auth_row)

    key_row = QHBoxLayout()
    key_row.addWidget(QLabel("Anthropic API Key:"))
    window.api_key_input = QLineEdit()
    window.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
    window.api_key_input.setPlaceholderText("sk-ant-api03-...")
    if window.claude_client.api_key:
        window.api_key_input.setText(window.claude_client.api_key)
    window.api_key_input.textChanged.connect(window.copilot_actions.on_api_key_changed)
    key_row.addWidget(window.api_key_input, 1)

    window.btn_toggle_key = QPushButton("Hiện/Ẩn Key")
    window.btn_toggle_key.clicked.connect(window.copilot_actions.toggle_key_visibility)
    key_row.addWidget(window.btn_toggle_key)
    auth_layout.addLayout(key_row)

    notice_label = QLabel(
        "Quyền riêng tư: Chỉ trích đoạn hội thoại (~3 phút) và tài liệu liên quan được gửi lên Anthropic API khi bấm nút. Biên bản không lưu vào đĩa."
    )
    notice_label.setStyleSheet("color: #475569; font-size: 11px; font-style: italic;")
    auth_layout.addWidget(notice_label)
    layout.addWidget(auth_box)

    # Card 2: Knowledge Documents & Meeting Context Snapshot
    store_row = QHBoxLayout()

    doc_box = QFrame()
    doc_box.setStyleSheet("QFrame { background-color: #faf5ff; border: 1px solid #e9d5ff; border-radius: 6px; }")
    doc_layout = QVBoxLayout(doc_box)
    doc_layout.setContentsMargins(8, 6, 8, 6)
    window.knowledge_status = QLabel("Tài liệu (.md, .txt): 0 tệp (0 đoạn)")
    window.knowledge_status.setStyleSheet("font-weight: 600; color: #6b21a8; font-size: 11px;")
    doc_layout.addWidget(window.knowledge_status)

    doc_btn_row = QHBoxLayout()
    btn_add_file = QPushButton("+ Thêm tệp")
    btn_add_file.clicked.connect(window.copilot_actions.add_knowledge_file)
    btn_add_dir = QPushButton("+ Thêm thư mục")
    btn_add_dir.clicked.connect(window.copilot_actions.add_knowledge_folder)
    btn_clear_doc = QPushButton("Xóa")
    btn_clear_doc.clicked.connect(window.copilot_actions.clear_knowledge)
    doc_btn_row.addWidget(btn_add_file)
    doc_btn_row.addWidget(btn_add_dir)
    doc_btn_row.addWidget(btn_clear_doc)
    doc_layout.addLayout(doc_btn_row)
    store_row.addWidget(doc_box, 1)

    ctx_box = QFrame()
    ctx_box.setStyleSheet("QFrame { background-color: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 6px; }")
    ctx_layout = QVBoxLayout(ctx_box)
    ctx_layout.setContentsMargins(8, 6, 8, 6)
    window.context_status = QLabel("Biên bản cuộc họp: 0 câu (0 từ)")
    window.context_status.setStyleSheet("font-weight: 600; color: #166534; font-size: 11px;")
    ctx_layout.addWidget(window.context_status)

    ctx_btn_row = QHBoxLayout()
    btn_review_ctx = QPushButton("Xem trước ngữ cảnh")
    btn_review_ctx.clicked.connect(window.copilot_actions.review_context_snapshot)
    btn_clear_ctx = QPushButton("Xóa biên bản")
    btn_clear_ctx.clicked.connect(window.copilot_actions.clear_meeting_context)
    ctx_btn_row.addWidget(btn_review_ctx)
    ctx_btn_row.addWidget(btn_clear_ctx)
    ctx_layout.addLayout(ctx_btn_row)
    store_row.addWidget(ctx_box, 1)
    layout.addLayout(store_row)

    # Card 3: Action & Question Input
    action_box = QFrame()
    action_layout = QVBoxLayout(action_box)
    action_layout.setContentsMargins(4, 2, 4, 2)
    action_layout.setSpacing(4)

    window.question_input = QLineEdit()
    window.question_input.setPlaceholderText("Câu hỏi hoặc yêu cầu cụ thể (để trống để tự động phân tích câu hỏi gần nhất trong cuộc họp)…")
    action_layout.addWidget(window.question_input)

    action_btn_row = QHBoxLayout()
    window.btn_help_reply = QPushButton("💬 Help Me Reply (Gợi ý câu trả lời)")
    window.btn_help_reply.setStyleSheet("font-weight: bold; background-color: #e0f2fe; color: #0369a1; padding: 6px 12px;")
    window.btn_help_reply.clicked.connect(lambda: window.copilot_actions.trigger_copilot("help_me_reply"))
    action_btn_row.addWidget(window.btn_help_reply)

    window.btn_explain = QPushButton("🔍 Explain Context (Giải thích cuộc họp)")
    window.btn_explain.clicked.connect(lambda: window.copilot_actions.trigger_copilot("explain_context"))
    action_btn_row.addWidget(window.btn_explain)

    window.btn_suggest = QPushButton("❓ Suggest Question (Gợi ý câu hỏi)")
    window.btn_suggest.clicked.connect(lambda: window.copilot_actions.trigger_copilot("suggest_question"))
    action_btn_row.addWidget(window.btn_suggest)

    window.btn_cancel_copilot = QPushButton("⏹ Hủy")
    window.btn_cancel_copilot.setEnabled(False)
    window.btn_cancel_copilot.clicked.connect(window.copilot_actions.cancel_copilot)
    action_btn_row.addWidget(window.btn_cancel_copilot)
    action_layout.addLayout(action_btn_row)
    layout.addWidget(action_box)

    # Card 4: Streaming English Response (Hero)
    ans_box = QFrame()
    ans_box.setStyleSheet("QFrame { background-color: #f8fafc; border: 1px solid #cbd5e1; border-radius: 8px; }")
    ans_layout = QVBoxLayout(ans_box)
    ans_layout.setContentsMargins(10, 8, 10, 8)
    ans_layout.setSpacing(4)

    ans_top_row = QHBoxLayout()
    ans_top_row.addWidget(QLabel("Suggested Spoken English (1-3 câu để nói ngay):"))
    ans_top_row.addStretch()
    window.btn_copy_english = QPushButton("📋 Copy English")
    window.btn_copy_english.clicked.connect(window.copilot_actions.copy_english_answer)
    ans_top_row.addWidget(window.btn_copy_english)
    ans_layout.addLayout(ans_top_row)

    window.english_answer_view = QTextEdit()
    window.english_answer_view.setReadOnly(True)
    window.english_answer_view.setStyleSheet("font-size: 15px; font-weight: bold; color: #0f172a; min-height: 70px;")
    ans_layout.addWidget(window.english_answer_view)
    layout.addWidget(ans_box, 1)

    # Card 5: Vietnamese Meaning & Evidence Citations
    details_row = QHBoxLayout()
    vi_box = QFrame()
    vi_box.setStyleSheet("QFrame { background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; }")
    vi_layout = QVBoxLayout(vi_box)
    vi_layout.setContentsMargins(8, 6, 8, 6)
    vi_layout.addWidget(QLabel("Ý nghĩa tiếng Việt (Vietnamese Meaning):"))
    window.vietnamese_meaning_view = QTextEdit()
    window.vietnamese_meaning_view.setReadOnly(True)
    window.vietnamese_meaning_view.setStyleSheet("color: #334155; font-size: 12px;")
    vi_layout.addWidget(window.vietnamese_meaning_view)
    details_row.addWidget(vi_box, 1)

    ev_box = QFrame()
    ev_box.setStyleSheet("QFrame { background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; }")
    ev_layout = QVBoxLayout(ev_box)
    ev_layout.setContentsMargins(8, 6, 8, 6)
    ev_layout.addWidget(QLabel("Dẫn chứng xác thực (Verified Evidence):"))
    window.evidence_view = QTextEdit()
    window.evidence_view.setReadOnly(True)
    window.evidence_view.setStyleSheet("color: #475569; font-size: 11px;")
    ev_layout.addWidget(window.evidence_view)
    details_row.addWidget(ev_box, 1)
    layout.addLayout(details_row, 1)

    # Copilot Metrics Bar
    window.copilot_metrics = QLabel("Copilot: Sẵn sàng  ·  Latency: —  ·  Tokens: —")
    window.copilot_metrics.setStyleSheet("color: #64748b; font-size: 11px;")
    layout.addWidget(window.copilot_metrics)

    return tab

