"""Meeting Assistant synthesizing local meeting context, documentation, and Claude Haiku 5.5."""

from __future__ import annotations

import threading
import time
from typing import Callable

from mac_live_translator.copilot.client import ClaudeClient
from mac_live_translator.copilot.models import CopilotResult, PreparedCopilotRequest
from mac_live_translator.copilot.parser import extract_citations, match_citations, parse_copilot_response
from mac_live_translator.copilot.prompts import SYSTEM_PROMPT, build_user_prompt
from mac_live_translator.copilot.streaming import StreamingSectionParser
from mac_live_translator.knowledge.store import KnowledgeStore
from mac_live_translator.meeting.context import MeetingContextStore
from mac_live_translator.meeting.memory_store import CompactedMemoryStore
from mac_live_translator.meeting.models import DetectedQuestion
from mac_live_translator.meeting.question import reconstruct_question_from_segments


class MeetingAssistant:
    """Orchestrates deterministic context retrieval, document retrieval, and Claude Haiku 5.5 streaming."""

    def __init__(
        self,
        context_store: MeetingContextStore,
        knowledge_store: KnowledgeStore,
        client: ClaudeClient,
        memory_store: CompactedMemoryStore | None = None,
    ) -> None:
        self.context_store = context_store
        self.knowledge_store = knowledge_store
        self.client = client
        self.memory_store = memory_store

    def prepare_request(
        self,
        action_type: str,
        user_query: str | None = None,
        unconfirmed_live_text: str = "",
    ) -> PreparedCopilotRequest:
        """Construct an immutable snapshot of retrieved meeting context, docs, and exact prompt."""
        t_start = time.monotonic()
        recent_segments = self.context_store.get_recent_snapshot(seconds=180.0, max_segments=30)

        effective_query = (user_query or "").strip()
        detected_question: DetectedQuestion | None = None

        if not effective_query:
            if action_type == "help_me_reply":
                detected_question = reconstruct_question_from_segments(recent_segments)
                if detected_question:
                    effective_query = detected_question.text
                else:
                    effective_query = "What is a helpful short comment or answer on the ongoing topic?"
            elif action_type == "explain_context":
                effective_query = "Summarize the technical decision, consensus, and key blockers discussed."
            elif action_type == "suggest_question":
                effective_query = "What is a smart, constructive technical question the developer should ask next?"

        recent_ids = {s.id for s in recent_segments}
        older_relevant = self.context_store.search_relevant(
            query=effective_query,
            top_k=4,
            include_neighbors=True,
            exclude_ids=recent_ids,
            max_words=350,
        )

        all_segments = sorted(recent_segments + older_relevant, key=lambda s: s.id)
        retrieved_docs = self.knowledge_store.search(effective_query, top_k=4)

        compacted_mem = self.memory_store.get_memory() if self.memory_store else None
        prompt_mem = compacted_mem.format_for_prompt() if (compacted_mem and not compacted_mem.is_empty()) else ""

        prompt_transcript = MeetingContextStore.format_for_prompt(all_segments, unconfirmed_live_text)
        prompt_docs = KnowledgeStore.format_for_prompt(retrieved_docs)
        user_prompt = build_user_prompt(
            prompt_transcript, prompt_docs, action_type, effective_query, prompt_memory=prompt_mem
        )
        prep_duration = time.monotonic() - t_start

        return PreparedCopilotRequest(
            action_type=action_type,
            effective_query=effective_query,
            detected_question=detected_question,
            recent_segments=recent_segments,
            older_segments=older_relevant,
            all_segments=all_segments,
            retrieved_docs=retrieved_docs,
            unconfirmed_live=unconfirmed_live_text,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            compacted_memory=compacted_mem,
            context_prep_duration=prep_duration,
            created_at=time.time(),
        )

    def execute_prepared_request(
        self,
        prepared: PreparedCopilotRequest,
        on_text: Callable[[str], None] | None = None,
        stop_event: threading.Event | None = None,
    ) -> CopilotResult:
        """Stream a previously prepared immutable request snapshot through Claude Haiku 5.5."""
        streaming_parser = StreamingSectionParser(on_text) if on_text else None

        raw_text, usage = self.client.stream_chat(
            system_prompt=prepared.system_prompt,
            user_message=prepared.user_prompt,
            on_text=streaming_parser.feed if streaming_parser else lambda t: None,
            stop_event=stop_event,
        )

        if streaming_parser:
            streaming_parser.finish()

        english_ans, viet_meaning, evidence_lines, warnings = parse_copilot_response(raw_text)

        valid_segments = {f"T#{s.id}": s.text for s in prepared.all_segments}
        if prepared.compacted_memory:
            for itm in prepared.compacted_memory.all_items():
                for sid in itm.source_ids:
                    valid_segments.setdefault(f"T#{sid}", f"[Memory] {itm.text}")
        valid_docs = {d.chunk_id: f"{d.filename} > {d.heading}: {d.text[:90]}..." for d in prepared.retrieved_docs}
        cited_ids = extract_citations(raw_text)
        matched_citations, unverified_citations = match_citations(cited_ids, valid_segments, valid_docs)

        usage.context_prep_duration = prepared.context_prep_duration

        return CopilotResult(
            action_type=prepared.action_type,
            english_answer=english_ans,
            vietnamese_meaning=viet_meaning,
            evidence_citations=matched_citations,
            unverified_citations=unverified_citations,
            warnings=warnings,
            raw_response=raw_text,
            usage=usage,
            retrieved_segments=prepared.all_segments,
            retrieved_docs=prepared.retrieved_docs,
            prepared_request=prepared,
        )

    def process_request(
        self,
        action_type: str,
        user_query: str | None = None,
        unconfirmed_live_text: str = "",
        on_text: Callable[[str], None] | None = None,
        stop_event: threading.Event | None = None,
    ) -> CopilotResult:
        """Prepare and immediately execute a Copilot request."""
        prepared = self.prepare_request(action_type, user_query, unconfirmed_live_text)
        return self.execute_prepared_request(prepared, on_text, stop_event)
