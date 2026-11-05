"""Dialogs, file pickers, and knowledge indexing for Meeting Copilot."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from mac_live_translator.gui.workers import KnowledgeIndexWorker
from mac_live_translator.meeting.context import MeetingContextStore

if TYPE_CHECKING:
    from mac_live_translator.gui.window import Window


def review_context_snapshot_dialog(win: Window) -> None:
    """Display dialog previewing recent meeting transcript excerpts sent to Claude."""
    recent = win.context_store.get_recent_snapshot(seconds=180.0, max_segments=30)
    unconfirmed = win.english_live.text()
    formatted = MeetingContextStore.format_for_prompt(recent, unconfirmed)
    dlg = QDialog(win)
    dlg.setWindowTitle("Xem trước ngữ cảnh gửi tới Claude")
    dlg.resize(600, 450)
    layout = QVBoxLayout(dlg)
    layout.addWidget(QLabel("Dưới đây là nội dung trích đoạn gần nhất (~3 phút) sẽ được gửi kèm câu hỏi:"))
    txt = QTextEdit()
    txt.setReadOnly(True)
    txt.setPlainText(formatted if formatted else "Chưa có biên bản nào được ghi nhận.")
    layout.addWidget(txt)
    btn = QPushButton("Đóng")
    btn.clicked.connect(dlg.accept)
    layout.addWidget(btn)
    dlg.exec()


def clear_meeting_context_dialog(win: Window, on_cleared: Callable[[], None]) -> None:
    """Prompt user confirmation before resetting meeting transcript memory."""
    reply = QMessageBox.question(
        win,
        "Xác nhận xóa biên bản",
        "Bạn có chắc chắn muốn xóa toàn bộ ngữ cảnh cuộc họp hiện tại?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )
    if reply == QMessageBox.StandardButton.Yes:
        on_cleared()


def add_knowledge_file_dialog(win: Window, on_index_path: Callable[[str], None]) -> None:
    """Open file picker for Markdown and TXT documentation."""
    paths, _ = QFileDialog.getOpenFileNames(
        win,
        "Chọn tệp tài liệu hỗ trợ",
        "",
        "Documents (*.md *.markdown *.txt)",
    )
    for p in paths:
        on_index_path(p)


def add_knowledge_folder_dialog(win: Window, on_index_path: Callable[[str], None]) -> None:
    """Open directory picker for documentation folder."""
    folder = QFileDialog.getExistingDirectory(win, "Chọn thư mục tài liệu")
    if folder:
        on_index_path(folder)


def clear_knowledge_action(win: Window) -> None:
    """Clear in-memory knowledge database and update UI label."""
    win.knowledge_store.clear()
    win.knowledge_status.setText("Tài liệu (.md, .txt): 0 tệp (0 đoạn)")


def index_knowledge_path(win: Window, path: str) -> None:
    """Start background worker to index selected file or folder into SQLite FTS5."""
    win.knowledge_status.setText(f"Đang nạp: {Path(path).name}…")
    worker = KnowledgeIndexWorker(win.knowledge_store, path)
    win.indexing_workers.add(worker)
    worker.indexing_done.connect(lambda added, p, w=worker: on_indexing_done(win, added, p, w))
    worker.indexing_failed.connect(lambda err, w=worker: on_indexing_failed(win, err, w))
    worker.start()


def on_indexing_done(win: Window, added: int, path: str, worker: KnowledgeIndexWorker) -> None:
    """Handle successful document indexing completion."""
    win.indexing_workers.discard(worker)
    files = win.knowledge_store.get_loaded_files()
    chunks = win.knowledge_store.get_chunk_count()
    win.knowledge_status.setText(f"Tài liệu (.md, .txt): {len(files)} tệp ({chunks} đoạn)")


def on_indexing_failed(win: Window, err: str, worker: KnowledgeIndexWorker) -> None:
    """Handle document indexing error and update status."""
    win.indexing_workers.discard(worker)
    win.knowledge_status.setText(f"Lỗi nạp: {err}")
