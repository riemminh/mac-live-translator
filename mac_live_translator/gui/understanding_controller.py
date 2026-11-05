"""Controller coordinating ContextEngine, background analysis worker, and Understanding UI."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox

from mac_live_translator.context_service.analyzer import SinglePassAnalysisResult
from mac_live_translator.context_service.models import BatchClaim
from mac_live_translator.gui.understanding_dashboard import render_dashboard
from mac_live_translator.gui.understanding_reading import UnderstandingReadingManager
from mac_live_translator.gui.workers import UnderstandingAnalysisWorker

if TYPE_CHECKING:
    from mac_live_translator.gui.window import Window


class UnderstandingController:
    """Manages Visual Understanding state, atomic batching, manual trigger, and dashboard."""

    def __init__(self, window: Window) -> None:
        self.win = window
        self.worker: UnderstandingAnalysisWorker | None = None
        self.active_generation = 1
        self.analysis_count = 0
        self.last_segment_time = 0.0
        self.last_error = ""
        self.reading = UnderstandingReadingManager(window)

        self.scheduler_timer = QTimer(self.win)
        self.scheduler_timer.setInterval(2000)
        self.scheduler_timer.timeout.connect(self._on_scheduler_tick)
        self.scheduler_timer.start()

    def bind_ui(self) -> None:
        """Bind understanding controls after UI panel initialization."""
        if hasattr(self.win, "btn_manual_analyze"):
            self.win.btn_manual_analyze.clicked.connect(self.on_manual_analyze_clicked)
        if hasattr(self.win, "understanding_auto_update"):
            self.win.understanding_auto_update.toggled.connect(self.on_auto_update_toggled)
        self.refresh_dashboard()

    def on_opt_in_toggled(self, checked: bool) -> None:
        if checked:
            if not self.win.claude_client.is_configured():
                QMessageBox.warning(self.win, "Thiếu API Key", "Vui lòng nhập Anthropic API Key (nút ⚙ Key) trước.")
                self.win.understanding_opt_in.setChecked(False)
                return
            reply = QMessageBox.question(
                self.win, "Bảo mật dữ liệu (Privacy Notice)",
                "Lưu ý: Khi bật, các trích đoạn tiếng Anh đã hoàn tất sẽ gửi tới Anthropic Claude qua API.\n"
                "Bạn có đồng ý bật phân tích đám mây không?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                self.win.understanding_opt_in.setChecked(False)
                return
            self.win.context_engine.set_cloud_opt_in(True)
            self.last_error = ""
            self.refresh_dashboard()
            if self._is_auto_update_enabled():
                self.check_and_trigger_analysis(force=False)
        else:
            self.win.context_engine.set_cloud_opt_in(False)
            if self.worker and self.worker.isRunning():
                self.worker.cancel()
            self._set_btn_enabled(True)
            self.refresh_dashboard()

    def _is_auto_update_enabled(self) -> bool:
        return not hasattr(self.win, "understanding_auto_update") or self.win.understanding_auto_update.isChecked()

    def _set_btn_enabled(self, enabled: bool) -> None:
        if hasattr(self.win, "btn_manual_analyze"):
            self.win.btn_manual_analyze.setEnabled(enabled)

    def on_auto_update_toggled(self, checked: bool) -> None:
        self.refresh_dashboard()
        if checked and self.win.understanding_opt_in.isChecked():
            self.check_and_trigger_analysis(force=False)

    def on_manual_analyze_clicked(self) -> None:
        """Handle manual update: verify opt-in, cooldown, pending content before running."""
        if not self.win.understanding_opt_in.isChecked():
            self.refresh_dashboard(notice="☁️ Chưa bật Claude — hãy bật quyền trước khi cập nhật.")
            return
        if self.worker and self.worker.isRunning():
            return
        session = self.win.context_engine.get_or_create_session("default")
        if session.is_analyzing:
            return

        cooldown = session.get_cooldown_remaining()
        if cooldown > 0:
            self.refresh_dashboard(notice=f"⏳ Vui lòng chờ {int(cooldown + 0.9)}s (cooldown) trước khi cập nhật tiếp.")
            return

        meaningful = session.count_meaningful_pending()
        if meaningful == 0:
            self.refresh_dashboard(notice="✅ Đã cập nhật — không có câu mới")
            return

        self.last_error = ""
        self._set_btn_enabled(False)
        self.check_and_trigger_analysis(force=True)

    def on_segment_finalized(self, segment_id: int, text: str, is_filler: bool = False) -> None:
        self.last_segment_time = time.monotonic()
        self.win.context_engine.add_segment("default", segment_id, text, is_filler)
        self.refresh_dashboard()
        if self.win.understanding_opt_in.isChecked() and self._is_auto_update_enabled():
            self.check_and_trigger_analysis(force=False)

    def _on_scheduler_tick(self) -> None:
        self.refresh_dashboard()
        if self.win.understanding_opt_in.isChecked() and self._is_auto_update_enabled():
            self.check_and_trigger_analysis(force=False)

    def check_and_trigger_analysis(self, force: bool = False) -> None:
        if not self.win.understanding_opt_in.isChecked() or (self.worker and self.worker.isRunning()):
            return
        if not force and not self._is_auto_update_enabled():
            return
        session = self.win.context_engine.get_session("default")
        if not session or session.is_analyzing:
            return

        self._set_btn_enabled(False)
        self.worker = UnderstandingAnalysisWorker(self.win.context_engine, session_id="default", force=force)
        self.worker.analysis_done.connect(self.on_analysis_success)
        self.worker.analysis_failed.connect(self.on_analysis_failed)
        self.worker.start()
        self.refresh_dashboard()

    def on_analysis_success(self, result: SinglePassAnalysisResult, claim: BatchClaim) -> None:
        self._set_btn_enabled(True)
        self.last_error = ""
        if claim.generation_id != self.active_generation:
            self.refresh_dashboard()
            return

        self.analysis_count += 1
        if self.win.freeze_checkbox.isChecked():
            feed = self.win.context_engine.get_feed("default", last_read_card_id=self.reading.last_read_card_id)
            unread = feed.unread_count if feed else 0
            self.reading.update_backlog(f"🔔 {unread} ý mới đang chờ", "#713f12", "#fef08a", True)
        else:
            self.reading.append_new_cards(result.meaning_cards)
            self.reading.update_meta(result.topic, result.pinned_question, result.decisions, result.action_items)
            self.reading.update_backlog("🔔 0 ý mới", "#27272a", "#a1a1aa", False)
        self.refresh_dashboard(notice=None)

    def on_analysis_failed(self, error_msg: str) -> None:
        self._set_btn_enabled(True)
        self.last_error = error_msg
        self.refresh_dashboard(notice=f"⚠️ Lỗi phân tích: {error_msg[:45]}…")

    def refresh_dashboard(self, notice: str | None = None) -> None:
        status = self.win.context_engine.get_understanding_status(
            session_id="default",
            auto_update=self._is_auto_update_enabled(),
            last_error=self.last_error,
        )
        render_dashboard(self.win, status, notice)
        if status.is_analyzing:
            self._set_btn_enabled(False)

    def on_freeze_toggled(self, checked: bool) -> None:
        self.reading.on_freeze_toggled(checked)

    def on_catchup_clicked(self) -> None:
        self.reading.on_catchup_clicked()

    def reset(self) -> None:
        self.active_generation += 1
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
        self._set_btn_enabled(True)
        self.last_error = ""
        self.reading.reset()
        self.refresh_dashboard()
