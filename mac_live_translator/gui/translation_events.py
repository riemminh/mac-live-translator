"""Event dispatchers and metric updates for live speech transcription and subtitles."""

from __future__ import annotations

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
            en_cue = win.subtitle_state.update_english(data["id"], data["text"])
            win.english_live.setText(en_cue)

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
            en_cue = win.subtitle_state.update_english(data["id"], data["text"])
            win.english_live.setText(en_cue)
        bi_entry = win.subtitle_state.record_final(data["id"], en_text=data["text"])
        if bi_entry:
            win.final_bi.insert(0, bi_entry)
            del win.final_bi[150:]
            show_history(win.bilingual, win.final_bi)
        win.context_store.add_segment(segment_id=data["id"], text=data["text"], is_filler=is_fill)
        win.copilot_actions.update_context_status()
        if hasattr(win, "understanding_controller"):
            win.understanding_controller.on_segment_finalized(data["id"], data["text"], is_fill)

    elif kind == "translation_revision":
        if data["revision"] > win.vi_revisions.get(data["id"], -1):
            win.vi_revisions[data["id"]] = data["revision"]
            preview = data.get("preview", "")
            if preview and win.current_id == data["id"]:
                active_cue, _ = win.subtitle_state.update_vietnamese(data["id"], preview, "stable")
                win.vietnamese_live.setText(active_cue)
                if hasattr(win, "compact_vi_live"):
                    win.compact_vi_live.setText(active_cue)

    elif kind == "vietnamese_partial" and data["id"] not in win.final_vi_ids:
        if data.get("revision", 0) < win.vi_revisions.get(data["id"], -1):
            return
        win.vi_revisions[data["id"]] = data.get("revision", 0)
        win.current_id = data["id"]
        status = data.get("status", "draft" if data.get("is_draft") else "stable")
        is_draft = (status == "draft")
        now = time.monotonic()
        if not data.get("is_filler", False):
            active_cue, _ = win.subtitle_state.update_vietnamese(data["id"], data["text"], status)
            win.vietnamese_live.setText(active_cue)
            if hasattr(win, "compact_vi_live"):
                win.compact_vi_live.setText(active_cue)
            if is_draft:
                win.vi_status_pill.setText("🟡 Dự kiến (Draft)")
                win.vi_status_pill.setStyleSheet("color: #facc15; font-size: 11px; font-weight: 600;")
                if data["id"] not in win.first_vietnamese_draft:
                    d_lat = data.get("latency", 0.0)
                    win.first_vietnamese_draft[data["id"]] = d_lat
                    win.draft_metric.setText(f"⏱ Nháp: {d_lat:.2f}s")
            else:
                win.vi_status_pill.setText("🔵 Ổn định (Stable)")
                win.vi_status_pill.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: 600;")
                if data["id"] not in win.first_vietnamese_rendered:
                    s_lat = data.get("latency", 0.0)
                    win.first_vietnamese_rendered[data["id"]] = s_lat
                    win.first_token_metric.setText(f"⏱ Ổn định: {s_lat:.2f}s")

    elif kind == "vietnamese_cancelled":
        if win.current_id == data["id"]:
            win.vietnamese_live.setText("Đang lắng nghe cuộc họp…")
            win.vi_status_pill.setText("🟢 Đang lắng nghe…")
            win.vi_status_pill.setStyleSheet("color: #4ade80; font-size: 11px; font-weight: 500;")

    elif kind == "vietnamese_final" and data["id"] not in win.final_vi_ids:
        win.final_vi_ids.add(data["id"])
        is_fill = data.get("is_filler", False)
        active_cue, _ = win.subtitle_state.update_vietnamese(data["id"], data["text"], "final")
        if not is_fill:
            win.vietnamese_live.setText(active_cue)
            if hasattr(win, "compact_vi_live"):
                win.compact_vi_live.setText(active_cue)
            win.recent_captions_label.setText(win.subtitle_state.get_recent_captions_display())
            win.vi_status_pill.setText("🟢 Hoàn tất (Final)")
            win.vi_status_pill.setStyleSheet("color: #4ade80; font-size: 11px; font-weight: 600;")
        tag = f"[{data['id']}]" + (" (filler)" if is_fill else "")
        win.final_vi.insert(0, f"{tag} {data['text']}")
        del win.final_vi[150:]
        show_history(win.vietnamese, win.final_vi)
        bi_entry = win.subtitle_state.record_final(data["id"], vi_text=data["text"])
        if bi_entry:
            win.final_bi.insert(0, bi_entry)
            del win.final_bi[150:]
            show_history(win.bilingual, win.final_bi)
        lat = data["latency"]
        win.final_metric.setText(f"⏱ Final: {lat:.2f}s")
        en_lat = win.first_english.get(data["id"], 0.0)
        d_lat = win.first_vietnamese_draft.get(data["id"], 0.0)
        s_lat = win.first_vietnamese_rendered.get(data["id"], 0.0)
        win.results.append((en_lat, d_lat, s_lat, lat))

    elif kind == "coverage":
        if hasattr(win, "queue_metric"):
            win.queue_metric.setText(f"📦 Hàng đợi: {data.get('queue_size', 0)}")

    elif kind == "status":
        win.status.setText(data["text"])

    elif kind == "stopped":
        win.vietnamese_live.setText("Đã dừng (Stopped)")
        if hasattr(win, "compact_vi_live"):
            win.compact_vi_live.setText("Đã dừng (Stopped)")
        win.english_live.setText("")
        win.vi_status_pill.setText("⚪ Đã dừng")
        win.vi_status_pill.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 500;")
        if hasattr(win, "listening_badge"):
            win.listening_badge.setText("⚪ Đã dừng (Stopped)")
        win.start_button.setEnabled(True)
        win.stop_button.setEnabled(False)
        win.status.setText("Stopped")
