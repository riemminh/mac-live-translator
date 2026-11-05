"""Dialogs, file pickers, and settings managers for Meeting Copilot."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from mac_live_translator.gui.workers import KnowledgeIndexWorker

if TYPE_CHECKING:
    from mac_live_translator.gui.window import Window


def open_settings_dialog(win: Window) -> None:
    """Dialog for configuring Anthropic API Key and model preferences."""
    dlg = QDialog(win)
    dlg.setWindowTitle("Cài đặt Claude AI & API Key")
    dlg.resize(460, 220)
    layout = QVBoxLayout(dlg)
    layout.setSpacing(10)

    layout.addWidget(QLabel("Anthropic API Key:"))
    key_input = QLineEdit()
    key_input.setEchoMode(QLineEdit.EchoMode.Password)
    key_input.setPlaceholderText("sk-ant-api03-...")
    if win.claude_client.api_key:
        key_input.setText(win.claude_client.api_key)
    layout.addWidget(key_input)

    btn_row = QHBoxLayout()
    btn_show = QPushButton("Hiện/Ẩn Key")
    def toggle() -> None:
        key_input.setEchoMode(QLineEdit.EchoMode.Normal if key_input.echoMode() == QLineEdit.EchoMode.Password else QLineEdit.EchoMode.Password)
    btn_show.clicked.connect(toggle)
    btn_row.addWidget(btn_show)
    btn_row.addStretch()

    btn_save = QPushButton("Lưu cấu hình")
    def save() -> None:
        win.claude_client.api_key = key_input.text().strip()
        win.ai_status_pill.setText("🟢 AI sẵn sàng\nClaude (Cloud)" if win.claude_client.is_configured() else "⚪ AI chưa cấu hình")
        dlg.accept()
    btn_save.clicked.connect(save)
    btn_row.addWidget(btn_save)
    layout.addLayout(btn_row)

    info = QLabel("Quyền riêng tư: API Key được lưu tạm trong bộ nhớ session, không ghi đè vào tệp công khai.")
    info.setStyleSheet("color: #94a3b8; font-size: 11px;")
    info.setWordWrap(True)
    layout.addWidget(info)
    dlg.exec()


def open_knowledge_dialog(win: Window) -> None:
    """Compact dialog managing loaded Markdown and TXT documentation."""
    dlg = QDialog(win)
    dlg.setWindowTitle("Quản lý tài liệu tham chiếu (Knowledge Files)")
    dlg.resize(480, 320)
    layout = QVBoxLayout(dlg)
    files = win.knowledge_store.get_loaded_files()

    layout.addWidget(QLabel(f"Danh sách tệp đã lập chỉ mục ({len(files)} tệp, {win.knowledge_store.get_chunk_count()} đoạn):"))
    txt = QTextEdit()
    txt.setReadOnly(True)
    txt.setPlainText("\n".join(f"• {f}" for f in files) if files else "Chưa nạp tài liệu nào (.md, .txt).")
    layout.addWidget(txt)

    btn_row = QHBoxLayout()
    for text, action in [
        ("+ Thêm tệp", lambda: add_knowledge_file_dialog(win, win.copilot_actions.index_knowledge_path)),
        ("+ Thêm thư mục", lambda: add_knowledge_folder_dialog(win, win.copilot_actions.index_knowledge_path)),
        ("Xóa tất cả", win.copilot_actions.clear_knowledge),
    ]:
        btn = QPushButton(text)
        btn.clicked.connect(lambda _, a=action: (a(), dlg.accept()))
        btn_row.addWidget(btn)
    layout.addLayout(btn_row)
    dlg.exec()


def review_context_snapshot_dialog(win: Window) -> None:
    """Display dialog previewing the exact immutable context snapshot prepared for Claude."""
    user_query = win.question_input.text().strip() or None
    unconfirmed = win.english_live.text().strip()
    if unconfirmed == "Waiting for speech…":
        unconfirmed = ""

    prepared = win.assistant.prepare_request(
        action_type="help_me_reply",
        user_query=user_query,
        unconfirmed_live_text=unconfirmed,
    )
    win.last_prepared_request = prepared

    dlg = QDialog(win)
    dlg.setWindowTitle("Xem trước nội dung gửi tới Claude (Source & Privacy Preview)")
    dlg.resize(680, 500)
    layout = QVBoxLayout(dlg)

    info_lbl = QLabel(
        "<b>Kiểm tra nội dung thực tế trước khi gửi lên Claude Haiku API:</b><br>"
        "Chỉ các trích đoạn biên bản và tài liệu dưới đây được chuyển giao. "
        "Không gửi toàn bộ thư mục hoặc thông tin tài khoản."
    )
    info_lbl.setWordWrap(True)
    info_lbl.setStyleSheet("color: #e2e8f0; font-size: 11px;")
    layout.addWidget(info_lbl)

    sections = []
    if prepared.detected_question:
        src_tags = ", ".join(f"T#{sid}" for sid in prepared.detected_question.source_ids)
        sections.append(f"[TỰ ĐỘNG PHÁT HIỆN CÂU HỎI ({src_tags})]\n{prepared.effective_query}\n")
    else:
        sections.append(f"[CÂU HỎI / YÊU CẦU]: {prepared.effective_query}\n")

    mem_tag = f" | TRÍ NHỚ: {prepared.compacted_memory.total_items_count()} mục" if prepared.compacted_memory and not prepared.compacted_memory.is_empty() else ""
    sections.append(
        f"[BIÊN BẢN GẦN NHẤT: {len(prepared.recent_segments)} câu | "
        f"LỊCH SỬ CŨ: {len(prepared.older_segments)} câu | "
        f"TÀI LIỆU: {len(prepared.retrieved_docs)} đoạn{mem_tag} | "
        f"Chuẩn bị: {prepared.context_prep_duration * 1000:.1f}ms]"
    )
    sections.append("\n" + "=" * 60 + "\nNỘI DUNG PROMPT HOÀN CHỈNH SẼ GỬI LÊN CLAUDE:\n" + "=" * 60)
    sections.append(prepared.user_prompt)

    txt = QTextEdit()
    txt.setReadOnly(True)
    txt.setPlainText("\n".join(sections))
    txt.setStyleSheet("font-family: monospace; font-size: 11px; background-color: #17151e; color: #e2e8f0;")
    layout.addWidget(txt)

    btn_row = QHBoxLayout()
    btn_send = QPushButton("🚀 Gửi dữ liệu này tới Claude ngay")
    btn_send.setStyleSheet("font-weight: bold; background-color: #6d28d9; color: white; padding: 6px 12px;")
    btn_send.clicked.connect(lambda: (dlg.accept(), win.copilot_actions.trigger_copilot_with_prepared(prepared)))
    btn_close = QPushButton("Đóng")
    btn_close.clicked.connect(dlg.reject)
    btn_row.addWidget(btn_send)
    btn_row.addWidget(btn_close)
    layout.addLayout(btn_row)
    dlg.exec()


def clear_meeting_context_dialog(win: Window, on_cleared: Callable[[], None]) -> None:
    reply = QMessageBox.question(
        win,
        "Xác nhận xóa biên bản",
        "Bạn có chắc chắn muốn xóa toàn bộ ngữ cảnh cuộc họp hiện tại?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )
    if reply == QMessageBox.StandardButton.Yes:
        on_cleared()


def add_knowledge_file_dialog(win: Window, on_index_path: Callable[[str], None]) -> None:
    paths, _ = QFileDialog.getOpenFileNames(win, "Chọn tệp tài liệu hỗ trợ", "", "Documents (*.md *.markdown *.txt)")
    for p in paths:
        on_index_path(p)


def add_knowledge_folder_dialog(win: Window, on_index_path: Callable[[str], None]) -> None:
    folder = QFileDialog.getExistingDirectory(win, "Chọn thư mục tài liệu")
    if folder:
        on_index_path(folder)


def index_knowledge_path(win: Window, path: str) -> None:
    win.knowledge_status.setText(f"Đang nạp: {Path(path).name}…")
    worker = KnowledgeIndexWorker(win.knowledge_store, path)
    win.indexing_workers.add(worker)
    worker.indexing_done.connect(lambda added, p, w=worker: on_indexing_done(win, added, p, w))
    worker.indexing_failed.connect(lambda err, w=worker: on_indexing_failed(win, err, w))
    worker.start()


def on_indexing_done(win: Window, added: int, path: str, worker: KnowledgeIndexWorker) -> None:
    win.indexing_workers.discard(worker)
    files = win.knowledge_store.get_loaded_files()
    chunks = win.knowledge_store.get_chunk_count()
    if hasattr(win, "knowledge_badge"):
        win.knowledge_badge.setText(f"{len(files)} tệp")
    win.knowledge_status.setText(f"{len(files)} tệp ({chunks} đoạn) >")


def on_indexing_failed(win: Window, err: str, worker: KnowledgeIndexWorker) -> None:
    win.indexing_workers.discard(worker)
    win.knowledge_status.setText(f"Lỗi nạp: {err}")
