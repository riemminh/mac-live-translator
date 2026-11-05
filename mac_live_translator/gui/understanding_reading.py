"""Manager for reading layout, meaning cards rendering, freeze state, and catch-up."""

from __future__ import annotations

from typing import TYPE_CHECKING
from mac_live_translator.context_service.models import MeaningCard
from mac_live_translator.gui.understanding_cards import CompactDecisionWidget, MeaningCardWidget

if TYPE_CHECKING:
    from mac_live_translator.gui.window import Window


class UnderstandingReadingManager:
    """Manages visual meaning card rendering, freeze reading, and paginated catch-up."""

    def __init__(self, window: Window) -> None:
        self.win = window
        self.displayed_card_ids: set[int] = set()
        self.last_read_card_id = 0

    def append_new_cards(self, cards: list[MeaningCard]) -> None:
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

    def update_meta(self, topic: str, pinned_q: str | None, decisions: list[dict], actions: list[dict]) -> None:
        """Update top topic, pinned discussion question, and confirmed decisions."""
        if topic:
            self.win.topic_label.setText(topic)
        self.win.pinned_question_label.setText(pinned_q or "")
        self.win.pinned_question_card.setVisible(bool(pinned_q))
        self.clear_layout(self.win.decisions_container)
        for d in decisions[:3]:
            self.win.decisions_container.addWidget(CompactDecisionWidget(d, is_action=False))
        for a in actions[:3]:
            self.win.decisions_container.addWidget(CompactDecisionWidget(a, is_action=True))

    def on_freeze_toggled(self, checked: bool) -> None:
        """Handle freeze toggle: catching up immediately when unfreezing."""
        if not checked:
            self.win.catchup_banner.setVisible(False)
            feed = self.win.context_engine.get_feed("default", last_read_card_id=0)
            if feed:
                self.displayed_card_ids.clear()
                self.clear_layout(self.win.cards_layout)
                self.win.cards_layout.addStretch()
                self.append_new_cards(feed.recent_cards)
                self.update_meta(feed.topic, feed.pinned_question, feed.decisions, feed.action_items)
            self.update_backlog("🔔 0 ý mới", "#27272a", "#a1a1aa", False)
            self.win.btn_catchup.setText("⚡ Bắt kịp (Catch Up)")

    def on_catchup_clicked(self) -> None:
        """Deterministic paginated catch-up without silently skipping unread cards."""
        catchup = self.win.context_engine.get_catchup("default", self.last_read_card_id, page_size=5)
        if catchup and catchup.unread_cards:
            self.win.catchup_banner.setText(f"⚡ {catchup.summary}")
            self.win.catchup_banner.setVisible(True)
            self.append_new_cards(catchup.unread_cards)
            self.last_read_card_id = catchup.last_read_card_id
            if catchup.has_more:
                self.update_backlog(f"🔔 còn {catchup.remaining_unread} ý", "#713f12", "#fef08a", True)
                self.win.btn_catchup.setText(f"⚡ Xem tiếp ({catchup.remaining_unread} ý)")
            else:
                self.update_backlog("🔔 0 ý mới", "#27272a", "#a1a1aa", False)
                self.win.btn_catchup.setText("⚡ Bắt kịp (Catch Up)")

    def update_backlog(self, text: str, bg: str, fg: str, btn_enabled: bool) -> None:
        self.win.backlog_badge.setText(text)
        self.win.backlog_badge.setStyleSheet(f"background-color: {bg}; color: {fg}; font-size: 10px; font-weight: 700; border-radius: 4px; padding: 2px 6px;")
        self.win.btn_catchup.setEnabled(btn_enabled)

    def reset(self) -> None:
        """Reset displayed cards and reading layout state."""
        self.last_read_card_id = 0
        self.displayed_card_ids.clear()
        self.win.topic_label.setText("Đang lắng nghe để xác định chủ đề…")
        self.win.pinned_question_card.setVisible(False)
        self.win.catchup_banner.setVisible(False)
        self.update_backlog("🔔 0 ý mới", "#27272a", "#a1a1aa", False)
        self.win.btn_catchup.setText("⚡ Bắt kịp (Catch Up)")
        self.clear_layout(self.win.cards_layout)
        self.win.cards_layout.addStretch()
        self.clear_layout(self.win.decisions_container)

    @staticmethod
    def clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

