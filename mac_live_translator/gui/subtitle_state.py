"""State manager for readable live subtitle cues, status tracking, and recent history."""

from __future__ import annotations

from collections import deque
from mac_live_translator.translation.cues import split_into_cues


class SubtitleState:
    """Encapsulates subtitle cue splitting, visual status, and reading continuity."""

    def __init__(self, max_recent: int = 2) -> None:
        self.recent_captions: deque[str] = deque(maxlen=max_recent)
        self.current_vi_cue: str = ""
        self.current_en_cue: str = ""
        self.current_segment_id: int | None = None
        self.status: str = "idle"  # "idle" | "draft" | "stable" | "final"
        self.finalized_en_map: dict[int, str] = {}
        self.finalized_vi_map: dict[int, str] = {}

    def reset(self) -> None:
        """Clear all active cues and recent captions on session stop or restart."""
        self.recent_captions.clear()
        self.current_vi_cue = ""
        self.current_en_cue = ""
        self.current_segment_id = None
        self.status = "idle"
        self.finalized_en_map.clear()
        self.finalized_vi_map.clear()

    def update_vietnamese(self, seg_id: int, full_text: str, status: str) -> tuple[str, list[str]]:
        """Process streaming or finalized Vietnamese, returning active cue and newly confirmed cues."""
        self.current_segment_id = seg_id
        self.status = status
        cues = split_into_cues(full_text, max_chars=75)
        if not cues:
            return "", []

        active_cue = cues[-1]
        self.current_vi_cue = active_cue

        newly_confirmed: list[str] = []
        if len(cues) > 1:
            for c in cues[:-1]:
                if not self.recent_captions or c != self.recent_captions[-1]:
                    self.recent_captions.append(c)
                    newly_confirmed.append(c)

        if status == "final":
            if not self.recent_captions or active_cue != self.recent_captions[-1]:
                self.recent_captions.append(active_cue)
                newly_confirmed.append(active_cue)

        return active_cue, newly_confirmed

    def update_english(self, seg_id: int, text: str) -> str:
        """Update the active English cue keeping only the most recent phrase visible."""
        self.current_segment_id = seg_id
        tokens = text.split()
        active_en = " ".join(tokens[-16:]) if len(tokens) > 16 else text
        self.current_en_cue = active_en
        return active_en

    def record_final(self, seg_id: int, en_text: str | None = None, vi_text: str | None = None) -> str | None:
        """Store finalized English/Vietnamese pair and return bilingual line if both ready."""
        if en_text is not None:
            self.finalized_en_map[seg_id] = en_text
        if vi_text is not None:
            self.finalized_vi_map[seg_id] = vi_text
        if seg_id in self.finalized_en_map and seg_id in self.finalized_vi_map:
            en = self.finalized_en_map[seg_id]
            vi = self.finalized_vi_map[seg_id]
            return f"[{seg_id}]\nEN: {en}\nVI: {vi}\n"
        return None

    def get_recent_captions_display(self) -> str:
        """Format recent confirmed captions into readable bullet points."""
        if not self.recent_captions:
            return "Chưa có phụ đề hoàn tất gần đây."
        return "\n".join(f"• {c}" for c in self.recent_captions)

