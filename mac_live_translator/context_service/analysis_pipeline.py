"""Pipeline executing analysis on an atomically claimed batch of transcript segments."""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

from mac_live_translator.context_service.analyzer import (
    SinglePassAnalysisResult,
    execute_single_pass_analysis,
)
from mac_live_translator.context_service.models import BatchClaim, UnderstandingStatus
from mac_live_translator.copilot.client import ClaudeClient

if TYPE_CHECKING:
    from mac_live_translator.context_service.session import SessionContext


def run_session_analysis(
    session: SessionContext,
    client: ClaudeClient,
    claim: BatchClaim,
    stop_event: threading.Event | None = None,
) -> tuple[SinglePassAnalysisResult, BatchClaim] | None:
    """Run retrieval, Claude Haiku single-pass analysis, and commit results or release claim."""
    try:
        batch_segs = [session.fts_store.get_segment(i) for i in claim.batch_ids]
        valid_segs = [s for s in batch_segs if s is not None and not s.is_filler]
        if not valid_segs:
            session.release_claim(claim)
            return None

        batch_text = "\n".join(f"[T#{s.segment_id}] {s.text}" for s in valid_segs)
        older_matches = session.fts_store.search(session.current_topic, top_k=3)
        evidence_segs = [m for m in older_matches if m.segment_id not in claim.batch_ids]
        older_text = "\n".join(f"[T#{m.segment_id}] {m.text}" for m in evidence_segs)

        valid_ids = {s.segment_id for s in valid_segs}.union(m.segment_id for m in evidence_segs)
        mem = session.memory_store.get_memory()
        mem_summary = mem.format_for_prompt(max_words=300) if not mem.is_empty() else ""

        result = execute_single_pass_analysis(
            client=client,
            batch_text=batch_text,
            valid_segment_ids=valid_ids,
            current_topic=session.current_topic,
            memory_summary=mem_summary,
            older_evidence=older_text,
            starting_card_id=session.next_card_id,
            stop_event=stop_event,
        )

        committed = session.commit_analysis(
            claim=claim,
            topic=result.topic,
            pinned_question=result.pinned_question,
            new_cards=result.meaning_cards,
            decisions=result.decisions,
            proposals=result.proposals,
            action_items=result.action_items,
            open_questions=result.open_questions,
            key_facts=result.key_facts,
            overview=result.memory_overview,
        )
        return (result, claim) if committed else None
    except Exception:
        session.release_claim(claim)
        raise


def evaluate_understanding_status(
    session: SessionContext | None,
    cloud_opt_in: bool,
    auto_update: bool = True,
    last_error: str = "",
) -> UnderstandingStatus:
    """Evaluate current understanding metrics, state, and next eligibility authoritatively."""
    if not session:
        return UnderstandingStatus(
            cloud_opt_in=cloud_opt_in, is_analyzing=False, pending_count=0,
            meaningful_pending=0, last_analyzed_id=None, last_success_time=0.0,
            cooldown_remaining=0.0, state="cloud_disabled" if not cloud_opt_in else "waiting_for_speech",
            next_eligible_desc="Chưa có phiên họp", auto_update_enabled=auto_update, last_error=last_error,
        )
    with session.lock:
        p_cnt = len(session.pending_segment_ids)
        m_cnt = sum(1 for sid in session.pending_segment_ids if (s := session.fts_store.get_segment(sid)) and not s.is_filler)
        last_id = max(session.analyzed_segment_ids) if session.analyzed_segment_ids else None
        last_ok = session.last_analysis_success_wall_time
        is_busy = session.is_analyzing
        now = time.monotonic()
        cd_rem = max(0.0, 15.0 - (now - session.last_analysis_attempt_time)) if session.last_analysis_attempt_time > 0 else 0.0
        elapsed = (now - session.batch_start_monotonic) if session.batch_start_monotonic > 0 else 0.0
        ready = (m_cnt >= 5) or (elapsed >= 25.0 and m_cnt >= 3)

        if not cloud_opt_in:
            desc = "Cloud chưa bật"
        elif not auto_update:
            desc = "Tự động tắt (bấm Cập nhật ngay)"
        elif is_busy:
            desc = "Đang phân tích…"
        elif p_cnt == 0:
            desc = "Đang chờ lời thoại mới"
        elif cd_rem > 0:
            desc = f"Chờ cooldown ({int(cd_rem + 0.9)}s)"
        elif ready:
            desc = "Sẵn sàng phân tích"
        elif m_cnt >= 3:
            desc = f"Đang chờ đủ câu ({m_cnt}/5 hoặc sau {max(0, int(25.0 - elapsed + 0.9))}s)"
        else:
            desc = f"Đang chờ đủ câu ({m_cnt}/5 câu)"

        if not cloud_opt_in:
            st = "cloud_disabled"
        elif is_busy:
            st = "analyzing"
        elif last_error:
            st = "failed"
        elif p_cnt == 0:
            st = "updated" if last_ok > 0 else "waiting_for_speech"
        elif cd_rem > 0:
            st = "cooldown"
        elif ready:
            st = "ready_to_analyze"
        else:
            st = "collecting_segments"

        return UnderstandingStatus(
            cloud_opt_in=cloud_opt_in, is_analyzing=is_busy, pending_count=p_cnt,
            meaningful_pending=m_cnt, last_analyzed_id=last_id, last_success_time=last_ok,
            cooldown_remaining=cd_rem, state=st, next_eligible_desc=desc,
            auto_update_enabled=auto_update, last_error=last_error,
        )
