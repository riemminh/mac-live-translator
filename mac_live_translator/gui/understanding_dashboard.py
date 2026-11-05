"""Dashboard widget presenting real-time analysis status, cooldown, and checkpoints."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from mac_live_translator.context_service.models import UnderstandingStatus
    from mac_live_translator.gui.window import Window

STATE_BADGES: dict[str, tuple[str, str, str, str]] = {
    "cloud_disabled": ("#24212e", "#94a3b8", "#382f49", "⚪ Ngoại tuyến (Tắt)"),
    "waiting_for_speech": ("#1e293b", "#94a3b8", "#334155", "⚪ Chờ lời thoại…"),
    "collecting_segments": ("#2e1065", "#d8b4fe", "#581c87", "⏳ Đang gom câu"),
    "ready_to_analyze": ("#064e3b", "#a7f3d0", "#047857", "🟢 Sẵn sàng phân tích"),
    "analyzing": ("#713f12", "#fef08a", "#a16207", "🟡 Đang phân tích…"),
    "updated": ("#064e3b", "#6ee7b7", "#059669", "✅ Đã cập nhật"),
    "cooldown": ("#451a03", "#fdba74", "#9a3412", "⏳ Cooldown"),
    "failed": ("#450a0a", "#fca5a5", "#991b1b", "🔴 Lỗi phân tích"),
}


def create_understanding_dashboard(window: Window) -> QWidget:
    """Build the real-time status dashboard showing Claude state and metrics."""
    card = QFrame()
    card.setStyleSheet("background-color: #171322; border: 1px solid #2e283b; border-radius: 8px;")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(10, 8, 10, 8)
    layout.setSpacing(5)

    # Top Header: Title + Status Pill
    top_row = QHBoxLayout()
    title_lbl = QLabel("📊 TRẠNG THÁI PHÂN TÍCH (CLAUDE)")
    title_lbl.setStyleSheet("color: #a78bfa; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")
    top_row.addWidget(title_lbl)
    top_row.addStretch()

    window.understanding_state_badge = QLabel("⚪ Ngoại tuyến (Tắt)")
    window.understanding_state_badge.setStyleSheet(
        "background-color: #24212e; color: #94a3b8; border: 1px solid #382f49; "
        "border-radius: 4px; padding: 2px 7px; font-size: 10px; font-weight: 700;"
    )
    top_row.addWidget(window.understanding_state_badge)
    layout.addLayout(top_row)

    # Grid of Metrics
    row1 = QHBoxLayout()
    window.dash_claude_lbl = QLabel("☁️ Claude: Chưa bật")
    window.dash_claude_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
    row1.addWidget(window.dash_claude_lbl, 1)

    window.dash_pending_lbl = QLabel("⏳ Đang chờ: 0 câu")
    window.dash_pending_lbl.setStyleSheet("color: #cbd5e1; font-size: 11px; font-weight: 600;")
    row1.addWidget(window.dash_pending_lbl, 1)
    layout.addLayout(row1)

    row2 = QHBoxLayout()
    window.dash_analyzed_lbl = QLabel("✅ Đã phân tích đến: —")
    window.dash_analyzed_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
    row2.addWidget(window.dash_analyzed_lbl, 1)

    window.dash_last_success_lbl = QLabel("🕒 Cập nhật thành công: —")
    window.dash_last_success_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
    row2.addWidget(window.dash_last_success_lbl, 1)
    layout.addLayout(row2)

    # Next eligible analysis indicator
    window.dash_next_lbl = QLabel("🔄 Lần phân tích tiếp theo: Cloud chưa bật")
    window.dash_next_lbl.setStyleSheet("color: #a1a1aa; font-size: 11px;")
    layout.addWidget(window.dash_next_lbl)

    # Notice banner for user feedback (cooldown countdown, empty updates, errors)
    window.dash_notice_lbl = QLabel("")
    window.dash_notice_lbl.setWordWrap(True)
    window.dash_notice_lbl.setStyleSheet(
        "background-color: #272018; border: 1px solid #78350f; color: #fde047; "
        "font-size: 10px; font-weight: 600; padding: 3px 6px; border-radius: 4px;"
    )
    window.dash_notice_lbl.setVisible(False)
    layout.addWidget(window.dash_notice_lbl)

    return card


def render_dashboard(
    window: Window,
    status: UnderstandingStatus,
    notice: str | None = None,
) -> None:
    """Render authoritative UnderstandingStatus into the dashboard UI elements."""
    # Claude Opt-In label
    if status.cloud_opt_in:
        window.dash_claude_lbl.setText("☁️ Claude: Được phép")
        window.dash_claude_lbl.setStyleSheet("color: #4ade80; font-size: 11px; font-weight: 600;")
    else:
        window.dash_claude_lbl.setText("☁️ Claude: Chưa bật")
        window.dash_claude_lbl.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 400;")

    # Pending count
    p_cnt = status.pending_count
    m_cnt = status.meaningful_pending
    suffix = f" ({m_cnt} có nghĩa)" if m_cnt != p_cnt and p_cnt > 0 else ""
    window.dash_pending_lbl.setText(f"⏳ Đang chờ: {p_cnt} câu{suffix}")
    p_color = "#fde047" if p_cnt >= 5 else ("#67e8f9" if p_cnt > 0 else "#94a3b8")
    window.dash_pending_lbl.setStyleSheet(f"color: {p_color}; font-size: 11px; font-weight: 600;")

    # Analyzed checkpoint
    if status.last_analyzed_id is not None:
        window.dash_analyzed_lbl.setText(f"✅ Đã phân tích đến: T#{status.last_analyzed_id}")
        window.dash_analyzed_lbl.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: 600;")
    else:
        window.dash_analyzed_lbl.setText("✅ Đã phân tích đến: —")
        window.dash_analyzed_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")

    # Last successful completion time
    if status.last_success_time > 0:
        ts = time.strftime("%H:%M:%S", time.localtime(status.last_success_time))
        window.dash_last_success_lbl.setText(f"🕒 Cập nhật thành công: {ts}")
        window.dash_last_success_lbl.setStyleSheet("color: #4ade80; font-size: 11px; font-weight: 500;")
    else:
        window.dash_last_success_lbl.setText("🕒 Cập nhật thành công: —")
        window.dash_last_success_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")

    # Next eligibility description
    window.dash_next_lbl.setText(f"🔄 Lần phân tích tiếp theo: {status.next_eligible_desc}")
    n_color = "#fde047" if "Sẵn sàng" in status.next_eligible_desc else "#a1a1aa"
    window.dash_next_lbl.setStyleSheet(f"color: {n_color}; font-size: 11px;")

    # State Badge
    bg, fg, border, label = STATE_BADGES.get(status.state, STATE_BADGES["cloud_disabled"])
    window.understanding_state_badge.setText(label)
    window.understanding_state_badge.setStyleSheet(
        f"background-color: {bg}; color: {fg}; border: 1px solid {border}; "
        f"border-radius: 4px; padding: 2px 7px; font-size: 10px; font-weight: 700;"
    )

    # Transient Notice
    if notice:
        window.dash_notice_lbl.setText(notice)
        window.dash_notice_lbl.setVisible(True)
    elif not window.dash_notice_lbl.text():
        window.dash_notice_lbl.setVisible(False)

