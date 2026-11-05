"""Dialog for inspecting compacted meeting memory, prompt preview, and manual compaction."""

from __future__ import annotations

from typing import TYPE_CHECKING
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from mac_live_translator.copilot.compactor import build_compaction_payload
from mac_live_translator.gui.workers import CompactionWorker

if TYPE_CHECKING:
    from mac_live_translator.gui.window import Window


def _format_memory_display(mem) -> str:
    """Format structured meeting memory into readable sections."""
    if mem.is_empty():
        return (
            "Chưa có trí nhớ được thu gọn.\n\n"
            "• Vùng bảo vệ: 30 câu gần nhất luôn được giữ nguyên văn thô.\n"
            "• Khi cuộc họp vượt quá 30 câu, các câu cũ sẽ đủ điều kiện để thu gọn.\n"
            "• Bấm nút '⚡ Thu gọn ngữ cảnh cũ' bên dưới để bắt đầu thu gọn."
        )
    out = [f"=== TỔNG QUAN CUỘC HỌP (Phiên bản: {mem.compaction_version}) ===\n{mem.overview}\n"]
    sec_map = [
        ("Quyết định đã thống nhất", mem.decisions),
        ("Kế hoạch hành động (Action Items)", mem.action_items),
        ("Câu hỏi còn mở (Open Questions)", mem.open_questions),
        ("Rủi ro & Trở ngại (Risks & Blockers)", mem.risks_blockers),
        ("Đề xuất & Ý tưởng", mem.proposals),
        ("Sự thật & Ràng buộc chính", mem.key_facts),
        ("Chủ đề đã thảo luận", mem.topics),
    ]
    for title, items in sec_map:
        if items:
            out.append(f"\n--- {title} ({len(items)}) ---")
            for itm in items:
                out.append(itm.format_line())
    return "\n".join(out)


def open_memory_dialog(win: Window) -> None:
    """Open the Compacted Meeting Memory and Context Inspector dialog."""
    dlg = QDialog(win)
    dlg.setWindowTitle("Trí nhớ cuộc họp đã thu gọn (Compacted Meeting Memory)")
    dlg.resize(720, 560)
    layout = QVBoxLayout(dlg)
    layout.setSpacing(8)

    stat_lbl = QLabel()
    stat_lbl.setStyleSheet("font-size: 11px; color: #a1a1aa; padding: 4px; background: #1a1622; border-radius: 6px;")
    layout.addWidget(stat_lbl)

    tabs = QTabWidget()
    mem_tab = QWidget()
    mem_layout = QVBoxLayout(mem_tab)
    mem_layout.setContentsMargins(0, 4, 0, 0)
    mem_text = QTextEdit()
    mem_text.setReadOnly(True)
    mem_text.setStyleSheet("font-family: monospace; font-size: 11px; background-color: #17151e; color: #e2e8f0;")
    mem_layout.addWidget(mem_text)
    tabs.addTab(mem_tab, "🧠 Trí nhớ đã thu gọn")

    prev_tab = QWidget()
    prev_layout = QVBoxLayout(prev_tab)
    prev_layout.setContentsMargins(0, 4, 0, 0)
    prev_text = QTextEdit()
    prev_text.setReadOnly(True)
    prev_text.setStyleSheet("font-family: monospace; font-size: 11px; background-color: #17151e; color: #94a3b8;")
    prev_layout.addWidget(prev_text)
    tabs.addTab(prev_tab, "🔍 Xem trước prompt gửi AI")
    layout.addWidget(tabs, 1)

    def refresh_views() -> None:
        summary = win.memory_store.get_compaction_summary(win.context_store)
        total_segs = len(win.context_store.get_all_entries())
        stat_lbl.setText(
            f"Tổng biên bản: {total_segs} câu | Vùng bảo vệ nguyên văn: 30 câu gần nhất | "
            f"Đã thu gọn tới: T#{summary['last_compacted_id']} (v{summary['compaction_version']}) | "
            f"Đang chờ thu gọn: {summary['pending_eligible_segments']} câu"
        )
        mem = win.memory_store.get_memory()
        mem_text.setPlainText(_format_memory_display(mem))

        candidates = win.memory_store.get_eligible_batch(win.context_store, min_batch=1)
        if candidates:
            sys_p, usr_p = build_compaction_payload(mem, candidates)
            prev_text.setPlainText(f"=== SYSTEM PROMPT ===\n{sys_p}\n\n=== USER PROMPT ===\n{usr_p}")
        else:
            prev_text.setPlainText("Hiện không có câu thoại cũ nào đủ điều kiện thu gọn (cần >30 câu trong biên bản).")

    refresh_views()

    btn_row = QHBoxLayout()
    btn_compact = QPushButton("⚡ Thu gọn ngữ cảnh cũ")
    btn_compact.setStyleSheet("font-weight: bold; background-color: #6d28d9; color: white; padding: 6px 12px;")

    def on_compact_click() -> None:
        if not win.cloud_opt_in.isChecked() or not win.claude_client.is_configured():
            QMessageBox.warning(dlg, "Chưa bật Cloud AI", "Vui lòng bật 'Sử dụng Claude AI' và nhập API Key.")
            return
        candidates = win.memory_store.get_eligible_batch(win.context_store, min_batch=1)
        if not candidates:
            QMessageBox.information(dlg, "Chưa có nội dung cần thu gọn", "Biên bản cần >30 câu để có nội dung cũ thu gọn.")
            return

        btn_compact.setEnabled(False)
        btn_compact.setText("⏳ Đang thu gọn qua Claude...")

        worker = CompactionWorker(win.claude_client, win.memory_store, win.context_store, min_batch=1, force=True)
        win.compaction_worker = worker

        def on_done(updated_mem, usage) -> None:
            btn_compact.setEnabled(True)
            btn_compact.setText("⚡ Thu gọn ngữ cảnh cũ")
            refresh_views()
            win.copilot_actions.update_context_status()
            QMessageBox.information(
                dlg, "Hoàn tất thu gọn",
                f"Đã cập nhật trí nhớ (v{updated_mem.compaction_version})!\n"
                f"Mục thông tin: {updated_mem.total_items_count()} | Tokens: {usage.input_tokens}+{usage.output_tokens}",
            )

        def on_fail(err) -> None:
            btn_compact.setEnabled(True)
            btn_compact.setText("⚡ Thu gọn ngữ cảnh cũ")
            refresh_views()
            QMessageBox.critical(dlg, "Lỗi thu gọn", f"Thu gọn thất bại: {err}")

        worker.compaction_done.connect(on_done)
        worker.compaction_failed.connect(on_fail)
        worker.start()

    btn_compact.clicked.connect(on_compact_click)
    btn_row.addWidget(btn_compact)

    btn_clear = QPushButton("🗑 Xóa biên bản & trí nhớ")
    btn_clear.clicked.connect(lambda: (win.copilot_actions.clear_meeting_context(), refresh_views()))
    btn_row.addWidget(btn_clear)
    btn_row.addStretch()

    btn_close = QPushButton("Đóng")
    btn_close.clicked.connect(dlg.accept)
    btn_row.addWidget(btn_close)
    layout.addLayout(btn_row)

    dlg.exec()

