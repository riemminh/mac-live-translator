"""Action controllers and worker lifecycle for Meeting Copilot requests."""

from __future__ import annotations

from typing import TYPE_CHECKING
from PySide6.QtWidgets import QApplication, QLineEdit, QMessageBox

from mac_live_translator.copilot.assistant import CopilotResult
from mac_live_translator.gui.copilot_panels import (
    add_knowledge_file_dialog,
    add_knowledge_folder_dialog,
    clear_knowledge_action,
    clear_meeting_context_dialog,
    index_knowledge_path,
    review_context_snapshot_dialog,
)
from mac_live_translator.gui.workers import CopilotWorker

if TYPE_CHECKING:
    from mac_live_translator.gui.window import Window


class CopilotActionsHandler:
    """Manages actions, request triggers, and worker callbacks for Meeting Copilot."""

    def __init__(self, window: Window) -> None:
        self.win = window

    def on_opt_in_toggled(self, checked: bool) -> None:
        if checked and not self.win.claude_client.is_configured():
            QMessageBox.information(
                self.win,
                "API Key Required",
                "Vui lòng nhập Anthropic API Key hợp lệ trước khi bật Cloud Assistance Opt-In.",
            )
            self.win.cloud_opt_in.setChecked(False)

    def on_api_key_changed(self, text: str) -> None:
        self.win.claude_client.api_key = text.strip()

    def on_model_changed(self, model_name: str) -> None:
        self.win.claude_client.model = model_name

    def toggle_key_visibility(self) -> None:
        if self.win.api_key_input.echoMode() == QLineEdit.EchoMode.Password:
            self.win.api_key_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.win.btn_toggle_key.setText("Ẩn Key")
        else:
            self.win.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.win.btn_toggle_key.setText("Hiện Key")

    def add_knowledge_file(self) -> None:
        add_knowledge_file_dialog(self.win, self.index_knowledge_path)

    def add_knowledge_folder(self) -> None:
        add_knowledge_folder_dialog(self.win, self.index_knowledge_path)

    def clear_knowledge(self) -> None:
        clear_knowledge_action(self.win)

    def index_knowledge_path(self, path: str) -> None:
        index_knowledge_path(self.win, path)

    def review_context_snapshot(self) -> None:
        review_context_snapshot_dialog(self.win)

    def clear_meeting_context(self) -> None:
        def perform_clear() -> None:
            self.win.copilot_generation_id += 1
            if self.win.copilot_worker and self.win.copilot_worker.isRunning():
                self.win.copilot_worker.cancel()
                self.reset_copilot_buttons()
            self.win.context_store.clear()
            self.win.recent_thought_groups.clear()
            self.win.context_label.setText("Ngữ cảnh gần nhất: —")
            self.win.context_status.setText("Biên bản cuộc họp: 0 câu (0 từ)")
            self.win.english_answer_view.clear()
            self.win.vietnamese_meaning_view.clear()
            self.win.evidence_view.clear()

        clear_meeting_context_dialog(self.win, perform_clear)

    def update_context_status(self) -> None:
        stats = self.win.context_store.get_context_summary()
        self.win.context_status.setText(
            f"Biên bản cuộc họp: {stats['total_segments']} câu ({stats['total_words']} từ)"
        )

    def copy_english_answer(self) -> None:
        text = self.win.english_answer_view.toPlainText().strip()
        if text:
            QApplication.clipboard().setText(text)
            self.win.copilot_metrics.setText("Copilot: Đã sao chép câu trả lời tiếng Anh vào clipboard!")

    def trigger_copilot(self, action_type: str) -> None:
        if not self.win.cloud_opt_in.isChecked():
            QMessageBox.warning(
                self.win,
                "Cloud Copilot Disabled",
                "Vui lòng bật 'Cho phép sử dụng Claude AI (Cloud Assistance Opt-In)' và cung cấp API Key trước khi gửi yêu cầu.",
            )
            return

        if not self.win.claude_client.is_configured():
            QMessageBox.warning(
                self.win,
                "API Key Missing",
                "Chưa có Anthropic API Key. Vui lòng nhập API Key để tiếp tục.",
            )
            return

        if self.win.copilot_worker and self.win.copilot_worker.isRunning():
            return

        self.win.copilot_generation_id += 1
        current_gen = self.win.copilot_generation_id
        user_query = self.win.question_input.text().strip() or None
        unconfirmed = self.win.english_live.text().strip()

        self.win.btn_help_reply.setEnabled(False)
        self.win.btn_explain.setEnabled(False)
        self.win.btn_suggest.setEnabled(False)
        self.win.btn_cancel_copilot.setEnabled(True)
        self.win.english_answer_view.clear()
        self.win.vietnamese_meaning_view.clear()
        self.win.evidence_view.clear()
        self.win.copilot_metrics.setText(f"Copilot: Đang kết nối tới Claude Haiku ({action_type})…")

        self.win.copilot_worker = CopilotWorker(
            assistant=self.win.assistant,
            action_type=action_type,
            user_query=user_query,
            unconfirmed_live=unconfirmed,
        )
        self.win.copilot_worker.chunk_received.connect(
            lambda token, gen=current_gen: self.on_copilot_token(token, gen)
        )
        self.win.copilot_worker.finished_success.connect(
            lambda res, gen=current_gen: self.on_copilot_success(res, gen)
        )
        self.win.copilot_worker.failed_error.connect(
            lambda err, gen=current_gen: self.on_copilot_error(err, gen)
        )
        self.win.copilot_worker.start()

    def cancel_copilot(self) -> None:
        self.win.copilot_generation_id += 1
        if self.win.copilot_worker and self.win.copilot_worker.isRunning():
            self.win.copilot_worker.cancel()
            self.win.copilot_metrics.setText("Copilot: Đã hủy yêu cầu.")
            self.reset_copilot_buttons()

    def on_copilot_token(self, token: str, gen_id: int) -> None:
        if gen_id != self.win.copilot_generation_id:
            return
        self.win.english_answer_view.insertPlainText(token)
        scrollbar = self.win.english_answer_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def on_copilot_success(self, result: CopilotResult, gen_id: int) -> None:
        if gen_id != self.win.copilot_generation_id:
            return
        self.win.english_answer_view.setPlainText(result.english_answer)
        self.win.vietnamese_meaning_view.setPlainText(result.vietnamese_meaning)

        ev_lines = []
        if result.evidence_citations:
            ev_lines.append("Trích dẫn khớp nguồn trích đoạn:")
            ev_lines.extend(f" • {c}" for c in result.evidence_citations)
        if result.unverified_citations:
            ev_lines.append("\nCảnh báo trích dẫn không có trong nguồn:")
            ev_lines.extend(f" ⚠️ {c}" for c in result.unverified_citations)
        if result.warnings:
            ev_lines.append("\nLưu ý & Điểm chưa rõ:")
            ev_lines.extend(f" ℹ️ {w}" for w in result.warnings)

        self.win.evidence_view.setPlainText("\n".join(ev_lines) if ev_lines else "Không có trích dẫn bổ sung.")
        usage = result.usage
        self.win.copilot_metrics.setText(
            f"Copilot: Hoàn thành ({usage.model}) · TTFT: {usage.time_to_first_token:.2f}s · "
            f"Tổng: {usage.total_duration:.2f}s · In/Out: {usage.input_tokens}/{usage.output_tokens} tokens"
        )
        self.reset_copilot_buttons()

    def on_copilot_error(self, err_msg: str, gen_id: int) -> None:
        if gen_id != self.win.copilot_generation_id:
            return
        self.win.copilot_metrics.setText(f"Copilot lỗi: {err_msg}")
        self.win.vietnamese_meaning_view.setPlainText(f"Lỗi xử lý yêu cầu: {err_msg}")
        self.reset_copilot_buttons()

    def reset_copilot_buttons(self) -> None:
        self.win.btn_help_reply.setEnabled(True)
        self.win.btn_explain.setEnabled(True)
        self.win.btn_suggest.setEnabled(True)
        self.win.btn_cancel_copilot.setEnabled(False)
