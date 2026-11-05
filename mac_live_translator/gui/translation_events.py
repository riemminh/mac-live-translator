"""Event dispatchers and metric updates for live speech transcription and subtitles."""

from __future__ import annotations

import statistics
import time
from typing import TYPE_CHECKING
from PySide6.QtWidgets import QTextEdit

if TYPE_CHECKING:
    from mac_live_translator.gui.window import Window


def show_history(view: QTextEdit, lines: list[str]) -> None:
    """Update a transcript view preserving scroll position unless at the bottom."""
    scrollbar = view.verticalScrollBar()
    old_pos, old_max = scrollbar.value(), scrollbar.maximum()
    view.setPlainText("\n".join(lines))
    if old_pos:
        scrollbar.setValue(old_pos + scrollbar.maximum() - old_max)
    else:
        scrollbar.setValue(0)


def handle_translation_event(win: Window, kind: str, data: dict) -> None:
    """Route and process incoming background pipeline events into the UI."""
    if kind == "english_partial" and data["id"] not in win.final_en_ids:
        if win.current_id is not None and data["id"] < win.current_id:
            return
        win.current_id = data["id"]
        win.first_english.setdefault(data["id"], data["latency"])
        if not data.get("is_filler", False):
            win.english_live.setText(f"{data['text']}")
        if hasattr(win, "first_token_metric"):
            rendered_vi = win.first_vietnamese_rendered.get(data["id"])
            vi_str = f"{rendered_vi:.2f}s" if rendered_vi is not None else "—"
            win.first_token_metric.setText(f"⏱ First: {vi_str}")

    elif kind == "english_final" and data["id"] not in win.final_en_ids:
        win.first_english.setdefault(data["id"], data["latency"])
        win.final_en_ids.add(data["id"])
        win.current_id = data["id"]
        is_fill = data.get("is_filler", False)
        tag = f"[{data['id']}]" + (" (filler)" if is_fill else "")
        win.final_en.insert(0, f"{tag} {data['text']}")
        del win.final_en[150:]
        show_history(win.english, win.final_en)
        if not is_fill:
            win.english_live.setText(data["text"])
        win.context_store.add_segment(segment_id=data["id"], text=data["text"], is_filler=is_fill)
        win.copilot_actions.update_context_status()

    elif kind == "translation_revision":
        if data["revision"] > win.vi_revisions.get(data["id"], -1):
            win.vi_revisions[data["id"]] = data["revision"]
            if win.preview_id == data["id"]:
                preview = data.get("preview", "")
                win.vietnamese_live.setText(f"{preview}" if preview else "Đang dịch…")

    elif kind == "vietnamese_partial" and data["id"] not in win.final_vi_ids:
        if data.get("revision", 0) < win.vi_revisions.get(data["id"], -1):
            return
        win.vi_revisions[data["id"]] = data.get("revision", 0)
        if win.preview_id is not None and data["id"] < win.preview_id:
            return
        win.preview_id = data["id"]
        now = time.monotonic()
        if not data.get("is_filler", False):
            win.vietnamese_live.setText(f"{data['text']}")
            if hasattr(win, "vi_status_pill"):
                win.vi_status_pill.setText("🟢 Đang dịch…")
            trace = win.traces.setdefault(data["id"], {})
            origin = trace.get("source_start")
            if data["id"] not in win.first_vietnamese_rendered:
                rendered_lat = (now - origin) if origin is not None else data["latency"]
                win.first_vietnamese_rendered[data["id"]] = rendered_lat
                if hasattr(win, "first_token_metric"):
                    win.first_token_metric.setText(f"⏱ First: {rendered_lat:.2f}s")
                if hasattr(win, "latency_pill"):
                    win.latency_pill.setText(f"⚡ Độ trễ: ~{rendered_lat:.1f}s")
        win.first_vietnamese_received.setdefault(data["id"], data["latency"])

    elif kind == "vietnamese_cancelled":
        if win.preview_id == data["id"]:
            win.vietnamese_live.setText("Đang lắng nghe cuộc họp…")
            win.preview_id = None

    elif kind == "vietnamese_final" and data["id"] not in win.final_vi_ids:
        win.final_vi_ids.add(data["id"])
        is_fill = data.get("is_filler", False)
        tag = f"[{data['id']}]" + (" (filler)" if is_fill else "")
        win.final_vi.insert(0, f"{tag} {data['text']}")
        del win.final_vi[150:]
        show_history(win.vietnamese, win.final_vi)
        if not is_fill:
            win.recent_thought_groups.append(f"{data['text']}")
            win.context_label.setText("  •  ".join(win.recent_thought_groups))
            if win.preview_id == data["id"]:
                win.vietnamese_live.setText(f"{data['text']}")
                win.preview_id = None
        lat = data["latency"]
        if hasattr(win, "final_metric"):
            win.final_metric.setText(f"⏱ Final: {lat:.2f}s")
        if hasattr(win, "latency_pill"):
            win.latency_pill.setText(f"⚡ Độ trễ: ~{lat:.1f}s")
        first_en = win.first_english.get(data["id"], 0.0)
        win.results.append((first_en, lat, lat, lat))

    elif kind == "coverage":
        if hasattr(win, "queue_metric"):
            win.queue_metric.setText(f"📦 Hàng đợi: {data.get('queue_size', 0)}")

    elif kind == "status":
        win.status.setText(data["text"])

    elif kind == "stopped":
        win.vietnamese_live.setText("Đã dừng (Stopped)")
        win.english_live.setText("")
        win.preview_id = None
        if hasattr(win, "listening_badge"):
            win.listening_badge.setText("⚪ Đã dừng (Stopped)")
        if hasattr(win, "vi_status_pill"):
            win.vi_status_pill.setText("⚪ Đã dừng")
        win.start_button.setEnabled(True)
        win.stop_button.setEnabled(False)
        win.status.setText("Stopped")
