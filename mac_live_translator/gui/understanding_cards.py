"""Meaning card and decision item widgets for Visual Meeting Understanding."""

from __future__ import annotations

from typing import Any
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from mac_live_translator.context_service.models import MeaningCard

CATEGORY_STYLES = {
    "decision": ("#065f46", "#a7f3d0", "✅ QUYẾT ĐỊNH"),
    "action": ("#7c2d12", "#fed7aa", "📋 HÀNH ĐỘNG"),
    "key_point": ("#4c1d95", "#ddd6fe", "💡 Ý CHÍNH"),
    "question": ("#075985", "#bae6fd", "❓ CÂU HỎI"),
    "proposal": ("#78350f", "#fde68a", "💭 ĐỀ XUẤT"),
}


class MeaningCardWidget(QFrame):
    """Visual meaning card conveying one clear discussion point at a glance."""

    def __init__(self, card: MeaningCard) -> None:
        super().__init__()
        self.card_id = card.card_id
        self.setStyleSheet(
            "QFrame { background-color: #1b1726; border: 1px solid #362e45; border-radius: 8px; } "
            "QFrame:hover { border-color: #6366f1; background-color: #1e192c; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # Header Row
        head_layout = QHBoxLayout()
        head_layout.setSpacing(6)

        bg, fg, label_text = CATEGORY_STYLES.get(card.category, ("#334155", "#e2e8f0", "Ý CHÍNH"))
        badge = QLabel(label_text)
        badge.setStyleSheet(f"background-color: {bg}; color: {fg}; font-size: 10px; font-weight: 700; border-radius: 3px; padding: 1px 6px;")
        head_layout.addWidget(badge)

        if card.importance == "high":
            star = QLabel("⭐ Quan trọng")
            star.setStyleSheet("color: #facc15; font-size: 10px; font-weight: 600;")
            head_layout.addWidget(star)

        head_layout.addStretch()

        if card.source_ids:
            src_str = " · ".join(f"T#{i}" for i in card.source_ids[:3])
            src_lbl = QLabel(src_str)
            src_lbl.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 500;")
            head_layout.addWidget(src_lbl)

        layout.addLayout(head_layout)

        # Headline
        hl_lbl = QLabel(card.headline)
        hl_lbl.setWordWrap(True)
        hl_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        hl_lbl.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: 700; line-height: 1.35;")
        layout.addWidget(hl_lbl)

        # Bullet points with collapsible secondary bullets
        if card.bullet_points:
            first_b = card.bullet_points[0]
            b1_lbl = QLabel(f"• {first_b}")
            b1_lbl.setWordWrap(True)
            b1_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            b1_lbl.setStyleSheet("color: #cbd5e1; font-size: 11px; line-height: 1.3;")
            layout.addWidget(b1_lbl)

            sec_bullets = card.bullet_points[1:3]
            if sec_bullets:
                sec_box = QWidget()
                sec_layout = QVBoxLayout(sec_box)
                sec_layout.setContentsMargins(0, 0, 0, 0)
                sec_layout.setSpacing(2)
                for b in sec_bullets:
                    sub_lbl = QLabel(f"• {b}")
                    sub_lbl.setWordWrap(True)
                    sub_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                    sub_lbl.setStyleSheet("color: #94a3b8; font-size: 11px; line-height: 1.25; margin-left: 4px;")
                    sec_layout.addWidget(sub_lbl)
                sec_box.setVisible(False)
                layout.addWidget(sec_box)

                btn_toggle = QPushButton(f"▸ Xem thêm {len(sec_bullets)} chi tiết")
                btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_toggle.setStyleSheet(
                    "QPushButton { background: transparent; border: none; color: #818cf8; "
                    "font-size: 10px; font-weight: 600; text-align: left; padding: 1px 0; } "
                    "QPushButton:hover { color: #a5b4fc; text-decoration: underline; }"
                )

                def on_toggle(b=sec_box, btn=btn_toggle, n=len(sec_bullets)) -> None:
                    vis = not b.isVisible()
                    b.setVisible(vis)
                    btn.setText("▾ Thu gọn" if vis else f"▸ Xem thêm {n} chi tiết")

                btn_toggle.clicked.connect(on_toggle)
                layout.addWidget(btn_toggle)


class CompactDecisionWidget(QFrame):
    """Compact summary line for confirmed decisions and action items."""

    def __init__(self, item: dict[str, Any], is_action: bool = False) -> None:
        super().__init__()
        self.setStyleSheet("QFrame { background-color: #16121d; border: 1px solid #282234; border-radius: 5px; }")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        icon = "📋" if is_action else "✅"
        icon_lbl = QLabel(icon)
        layout.addWidget(icon_lbl)

        text_val = item.get("text", "")
        extra = []
        if item.get("owner"):
            extra.append(f"Người phụ trách: {item['owner']}")
        if item.get("deadline"):
            extra.append(f"Hạn: {item['deadline']}")
        extra_str = f" ({'; '.join(extra)})" if extra else ""

        desc_lbl = QLabel(f"{text_val}{extra_str}")
        desc_lbl.setWordWrap(True)
        desc_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        desc_lbl.setStyleSheet("color: #f1f5f9; font-size: 11px;")
        layout.addWidget(desc_lbl, 1)

        srcs = item.get("source_ids", [])
        if srcs:
            src_lbl = QLabel(f"[{', '.join(f'T#{i}' for i in srcs[:2])}]")
            src_lbl.setStyleSheet("color: #64748b; font-size: 9px; font-family: monospace;")
            layout.addWidget(src_lbl)

