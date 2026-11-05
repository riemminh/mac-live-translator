"""Controller coordinating ContextEngine, background analysis worker, and Understanding UI."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from PySide6.QtWidgets import QMessageBox

from mac_live_translator.context_service.analyzer import SinglePassAnalysisResult
from mac_live_translator.context_service.models import MeaningCard
from mac_live_translator.gui.understanding_cards import CompactDecisionWidget, MeaningCardWidget
from mac_live_translator.gui.workers import UnderstandingAnalysisWorker

if TYPE_CHECKING:
    from mac_live_translator.gui.window import Window


class UnderstandingController:
    """Manages Visual Understanding state, background batching, freeze, and catchup."""

    def __init__(self, window: Window) -> None:
        self.win = window
        self.worker: UnderstandingAnalysisWorker | None = None
        self.last_read_card_id = 0
        self.unread_backlog = 0
        self.analysis_count = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.last_segment_time = 0.0

    def on_opt_in_toggled(self, checked: bool) -> None:
        if checked:
            if not self.win.claude_client.is_configured():
                QMessageBox.warning(
                    self.win,
                    "Thiếu API Key",
                    "Vui lòng nhập Anthropic API Key (nút ⚙ Key) trước khi bật phân tích hiểu cuộc họp.",
                )
                self.win.understanding_opt_in.setChecked(False)
                return

            reply = QMessageBox.question(
                self.win,
                "Bảo mật dữ liệu (Privacy Notice)",
                "Lưu ý: Khi bật tính năng này, các trích đoạn tiếng Anh đã hoàn tất sẽ được gửi định kỳ "
                "tới Anthropic Claude qua API để tạo thẻ ý chính.\n\n"
                "Bạn có đồng ý bật phân tích đám mây không?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                self.win.understanding_opt_in.setChecked(False)
                return

            self.win.understanding_status_lbl.setText("🟢 Đang phân tích (Active)")
            self.win.understanding_status_lbl.setStyleSheet("color: #4ade80; font-size: 10px; font-weight: 600;")
            self.check_and_trigger_analysis()
        else:
            if self.worker and self.worker.isRunning():
                self.worker.cancel()
            self.win.understanding_status_lbl.setText("⚪ Ngoại tuyến (Offline)")
            self.win.understanding_status_lbl.setStyleSheet("color: #94a3b8; font-size: 10px;")

    def on_segment_finalized(self, segment_id: int, text: str, is_filler: bool = False) -> None:
        self.last_segment_time = time.monotonic()
        self.win.context_engine.add_segment("default", segment_id, text, is_filler)
        if self.win.understanding_opt_in.isChecked():
            self.check_and_trigger_analysis()

    def check_and_trigger_analysis(self, force: bool = False) -> None:
        if not self.win.understanding_opt_in.isChecked() or (self.worker and self.worker.isRunning()):
            return

        session = self.win.context_engine.get_session("default")
        if not session:
            return

        batch_ids = session.get_pending_batch(min_size=1 if force else 5)
        if not batch_ids:
            return

        self.worker = UnderstandingAnalysisWorker(self.win.context_engine, session_id="default", force=force)
        self.worker.analysis_done.connect(self.on_analysis_success)
        self.worker.analysis_failed.connect(self.on_analysis_failed)
        self.worker.start()

    def on_analysis_success(self, result: SinglePassAnalysisResult) -> None:
        self.analysis_count += 1
        self.total_input_tokens += result.usage.input_tokens
        self.total_output_tokens += result.usage.output_tokens
        time_to_card = time.monotonic() - self.last_segment_time if self.last_segment_time > 0 else 0.0

        if self.win.freeze_checkbox.isChecked():
            self.unread_backlog += len(result.meaning_cards)
            self.win.backlog_badge.setText(f"🔔 {self.unread_backlog} ý mới đang chờ")
            self.win.backlog_badge.setStyleSheet(
                "background-color: #713f12; color: #fef08a; font-size: 10px; font-weight: 700; border-radius: 4px; padding: 2px 6px;"
            )
            self.win.btn_catchup.setEnabled(True)
        else:
            self._apply_feed_update(result.topic, result.pinned_question, result.meaning_cards, result.decisions, result.action_items)
            self.unread_backlog = 0
            self.win.backlog_badge.setText("🔔 0 ý mới")
            self.win.backlog_badge.setStyleSheet(
                "background-color: #27272a; color: #a1a1aa; font-size: 10px; font-weight: 700; border-radius: 4px; padding: 2px 6px;"
            )
            self.win.btn_catchup.setEnabled(False)

        self.win.understanding_status_lbl.setText(
            f"🟢 Phân tích #{self.analysis_count} ({time_to_card:.1f}s) · In/Out: {result.usage.input_tokens}/{result.usage.output_tokens}"
        )

    def on_analysis_failed(self, error_msg: str) -> None:
        self.win.understanding_status_lbl.setText(f"⚠️ Lỗi phân tích: {error_msg[:40]}…")
        self.win.understanding_status_lbl.setStyleSheet("color: #f87171; font-size: 10px;")

    def _apply_feed_update(
        self,
        topic: str,
        pinned_question: str | None,
        cards: list[MeaningCard],
        decisions: list[dict],
        actions: list[dict],
    ) -> None:
        if topic:
            self.win.topic_label.setText(topic)
        if pinned_question:
            self.win.pinned_question_label.setText(pinned_question)
            self.win.pinned_question_card.setVisible(True)
        else:
            self.win.pinned_question_card.setVisible(False)

        # Re-populate recent cards (up to 5)
        feed = self.win.context_engine.get_feed("default", last_read_card_id=0)
        recent_cards = feed.recent_cards if feed else cards
        self._clear_layout(self.win.cards_layout)
        for c in recent_cards[-5:]:
            self.win.cards_layout.addWidget(MeaningCardWidget(c))
            self.last_read_card_id = max(self.last_read_card_id, c.card_id)
        self.win.cards_layout.addStretch()

        # Re-populate decisions & actions
        self._clear_layout(self.win.decisions_container)
        for d in (feed.decisions[:3] if feed else decisions[:3]):
            self.win.decisions_container.addWidget(CompactDecisionWidget(d, is_action=False))
        for a in (feed.action_items[:3] if feed else actions[:3]):
            self.win.decisions_container.addWidget(CompactDecisionWidget(a, is_action=True))

    def on_freeze_toggled(self, checked: bool) -> None:
        if not checked:
            self.win.catchup_banner.setVisible(False)
            feed = self.win.context_engine.get_feed("default", last_read_card_id=0)
            if feed:
                self._apply_feed_update(feed.topic, feed.pinned_question, feed.recent_cards, feed.decisions, feed.action_items)
            self.unread_backlog = 0
            self.win.backlog_badge.setText("🔔 0 ý mới")
            self.win.backlog_badge.setStyleSheet(
                "background-color: #27272a; color: #a1a1aa; font-size: 10px; font-weight: 700; border-radius: 4px; padding: 2px 6px;"
            )
            self.win.btn_catchup.setEnabled(False)

    def on_catchup_clicked(self) -> None:
        catchup = self.win.context_engine.get_catchup("default", self.last_read_card_id)
        if catchup and catchup.unread_cards:
            self.win.catchup_banner.setText(f"⚡ {catchup.summary}")
            self.win.catchup_banner.setVisible(True)
            feed = self.win.context_engine.get_feed("default", last_read_card_id=0)
            if feed:
                self._apply_feed_update(feed.topic, feed.pinned_question, feed.recent_cards, feed.decisions, feed.action_items)
            self.last_read_card_id = catchup.last_read_card_id
        self.unread_backlog = 0
        self.win.backlog_badge.setText("🔔 0 ý mới")
        self.win.backlog_badge.setStyleSheet(
            "background-color: #27272a; color: #a1a1aa; font-size: 10px; font-weight: 700; border-radius: 4px; padding: 2px 6px;"
        )
        self.win.btn_catchup.setEnabled(False)

    def reset(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
        self.last_read_card_id = 0
        self.unread_backlog = 0
        self.win.topic_label.setText("Đang lắng nghe để xác định chủ đề…")
        self.win.pinned_question_card.setVisible(False)
        self.win.catchup_banner.setVisible(False)
        self.win.backlog_badge.setText("🔔 0 ý mới")
        self.win.btn_catchup.setEnabled(False)
        self._clear_layout(self.win.cards_layout)
        self.win.cards_layout.addStretch()
        self._clear_layout(self.win.decisions_container)

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
