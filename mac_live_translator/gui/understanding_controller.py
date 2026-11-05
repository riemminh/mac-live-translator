"""Controller coordinating ContextEngine, background analysis worker, and Understanding UI."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox

from mac_live_translator.context_service.analyzer import SinglePassAnalysisResult
from mac_live_translator.context_service.models import BatchClaim, MeaningCard
from mac_live_translator.gui.understanding_cards import CompactDecisionWidget, MeaningCardWidget
from mac_live_translator.gui.workers import UnderstandingAnalysisWorker

if TYPE_CHECKING:
    from mac_live_translator.gui.window import Window


class UnderstandingController:
    """Manages Visual Understanding state, atomic batching, freeze, and paginated catch-up."""

    def __init__(self, window: Window) -> None:
        self.win = window
        self.worker: UnderstandingAnalysisWorker | None = None
        self.active_generation = 1
        self.last_read_card_id = 0
        self.analysis_count = 0
        self.displayed_card_ids: set[int] = set()
        self.last_segment_time = 0.0

        # Lightweight scheduler timer waking up every 2.5s to handle silence/timeouts
        self.scheduler_timer = QTimer(self.win)
        self.scheduler_timer.setInterval(2500)
        self.scheduler_timer.timeout.connect(self._on_scheduler_tick)
        self.scheduler_timer.start()

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
            self._set_status("🟢 Đang phân tích (Active)", "#4ade80", 600)
            self.check_and_trigger_analysis()
        else:
            self.win.context_engine.set_cloud_opt_in(False)
            if self.worker and self.worker.isRunning():
                self.worker.cancel()
            self._set_status("⚪ Ngoại tuyến (Offline)", "#94a3b8", 400)

    def _set_status(self, text: str, color: str, weight: int = 400) -> None:
        self.win.understanding_status_lbl.setText(text)
        self.win.understanding_status_lbl.setStyleSheet(f"color: {color}; font-size: 10px; font-weight: {weight};")

    def on_segment_finalized(self, segment_id: int, text: str, is_filler: bool = False) -> None:
        self.last_segment_time = time.monotonic()
        self.win.context_engine.add_segment("default", segment_id, text, is_filler)
        if self.win.understanding_opt_in.isChecked():
            self.check_and_trigger_analysis()

    def _on_scheduler_tick(self) -> None:
        if self.win.understanding_opt_in.isChecked():
            self.check_and_trigger_analysis()

    def check_and_trigger_analysis(self, force: bool = False) -> None:
        if not self.win.understanding_opt_in.isChecked() or (self.worker and self.worker.isRunning()):
            return
        session = self.win.context_engine.get_session("default")
        if not session or session.is_analyzing:
            return

        self.worker = UnderstandingAnalysisWorker(self.win.context_engine, session_id="default", force=force)
        self.worker.analysis_done.connect(self.on_analysis_success)
        self.worker.analysis_failed.connect(self.on_analysis_failed)
        self.worker.start()

    def on_analysis_success(self, result: SinglePassAnalysisResult, claim: BatchClaim) -> None:
        if claim.generation_id != self.active_generation:
            return  # Discard stale analysis from previous or reset session

        self.analysis_count += 1
        time_to_card = time.monotonic() - self.last_segment_time if self.last_segment_time > 0 else 0.0

        if self.win.freeze_checkbox.isChecked():
            feed = self.win.context_engine.get_feed("default", last_read_card_id=self.last_read_card_id)
            unread = feed.unread_count if feed else 0
            self._update_backlog(f"🔔 {unread} ý mới đang chờ", "#713f12", "#fef08a", True)
        else:
            self._append_new_cards(result.meaning_cards)
            self._update_meta(result.topic, result.pinned_question, result.decisions, result.action_items)
            self._update_backlog("🔔 0 ý mới", "#27272a", "#a1a1aa", False)

        self._set_status(
            f"🟢 #{self.analysis_count} ({time_to_card:.1f}s) · In/Out: {result.usage.input_tokens}/{result.usage.output_tokens}",
            "#4ade80",
        )

    def on_analysis_failed(self, error_msg: str) -> None:
        self._set_status(f"⚠️ Lỗi: {error_msg[:35]}…", "#f87171")

    def _update_backlog(self, text: str, bg: str, fg: str, btn_enabled: bool) -> None:
        self.win.backlog_badge.setText(text)
        self.win.backlog_badge.setStyleSheet(f"background-color: {bg}; color: {fg}; font-size: 10px; font-weight: 700; border-radius: 4px; padding: 2px 6px;")
        self.win.btn_catchup.setEnabled(btn_enabled)

    def _append_new_cards(self, cards: list[MeaningCard]) -> None:
        """Protect reading continuity: append newly arrived cards without wiping layout."""
        for c in cards:
            if c.card_id not in self.displayed_card_ids:
                widget = MeaningCardWidget(c)
                idx = max(0, self.win.cards_layout.count() - 1)
                self.win.cards_layout.insertWidget(idx, widget)
                self.displayed_card_ids.add(c.card_id)
                self.last_read_card_id = max(self.last_read_card_id, c.card_id)

        while self.win.cards_layout.count() > 6:
            item = self.win.cards_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

    def _update_meta(self, topic: str, pinned_q: str | None, decisions: list[dict], actions: list[dict]) -> None:
        if topic:
            self.win.topic_label.setText(topic)
        self.win.pinned_question_label.setText(pinned_q or "")
        self.win.pinned_question_card.setVisible(bool(pinned_q))

        self._clear_layout(self.win.decisions_container)
        for d in decisions[:3]:
            self.win.decisions_container.addWidget(CompactDecisionWidget(d, is_action=False))
        for a in actions[:3]:
            self.win.decisions_container.addWidget(CompactDecisionWidget(a, is_action=True))

    def on_freeze_toggled(self, checked: bool) -> None:
        if not checked:
            self.win.catchup_banner.setVisible(False)
            feed = self.win.context_engine.get_feed("default", last_read_card_id=0)
            if feed:
                self.displayed_card_ids.clear()
                self._clear_layout(self.win.cards_layout)
                self.win.cards_layout.addStretch()
                self._append_new_cards(feed.recent_cards)
                self._update_meta(feed.topic, feed.pinned_question, feed.decisions, feed.action_items)
            self._update_backlog("🔔 0 ý mới", "#27272a", "#a1a1aa", False)
            self.win.btn_catchup.setText("⚡ Bắt kịp (Catch Up)")

    def on_catchup_clicked(self) -> None:
        """Deterministic paginated catch-up without silently skipping unread cards."""
        catchup = self.win.context_engine.get_catchup("default", self.last_read_card_id, page_size=5)
        if catchup and catchup.unread_cards:
            self.win.catchup_banner.setText(f"⚡ {catchup.summary}")
            self.win.catchup_banner.setVisible(True)
            self._append_new_cards(catchup.unread_cards)
            self.last_read_card_id = catchup.last_read_card_id

            if catchup.has_more:
                self._update_backlog(f"🔔 còn {catchup.remaining_unread} ý", "#713f12", "#fef08a", True)
                self.win.btn_catchup.setText(f"⚡ Xem tiếp ({catchup.remaining_unread} ý)")
            else:
                self._update_backlog("🔔 0 ý mới", "#27272a", "#a1a1aa", False)
                self.win.btn_catchup.setText("⚡ Bắt kịp (Catch Up)")

    def reset(self) -> None:
        self.active_generation += 1
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
        self.last_read_card_id = 0
        self.displayed_card_ids.clear()
        self.win.topic_label.setText("Đang lắng nghe để xác định chủ đề…")
        self.win.pinned_question_card.setVisible(False)
        self.win.catchup_banner.setVisible(False)
        self._update_backlog("🔔 0 ý mới", "#27272a", "#a1a1aa", False)
        self.win.btn_catchup.setText("⚡ Bắt kịp (Catch Up)")
        self._clear_layout(self.win.cards_layout)
        self.win.cards_layout.addStretch()
        self._clear_layout(self.win.decisions_container)

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
