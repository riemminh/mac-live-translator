"""Meeting Assistant synthesizing local meeting context, documentation, and Claude Haiku 5.5."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from typing import Callable

from mac_live_translator.copilot.client import ClaudeClient, ClaudeUsage
from mac_live_translator.copilot.parser import extract_citations, match_citations, parse_copilot_response
from mac_live_translator.copilot.prompts import SYSTEM_PROMPT, build_user_prompt
from mac_live_translator.knowledge.models import DocumentChunk
from mac_live_translator.knowledge.store import KnowledgeStore
from mac_live_translator.meeting.context import MeetingContextStore
from mac_live_translator.meeting.models import TranscriptEntry


@dataclass
class CopilotResult:
    """Structured result returned by the Meeting Assistant."""
    action_type: str
    english_answer: str
    vietnamese_meaning: str
    evidence_citations: list[str] = field(default_factory=list)
    unverified_citations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw_response: str = ""
    usage: ClaudeUsage = field(default_factory=ClaudeUsage)
    retrieved_segments: list[TranscriptEntry] = field(default_factory=list)
    retrieved_docs: list[DocumentChunk] = field(default_factory=list)


class MeetingAssistant:
    """Orchestrates deterministic context retrieval, document retrieval, and Claude Haiku 5.5 streaming."""

    def __init__(
        self,
        context_store: MeetingContextStore,
        knowledge_store: KnowledgeStore,
        client: ClaudeClient,
    ) -> None:
        self.context_store = context_store
        self.knowledge_store = knowledge_store
        self.client = client

    def process_request(
        self,
        action_type: str,
        user_query: str | None = None,
        unconfirmed_live_text: str = "",
        on_text: Callable[[str], None] | None = None,
        stop_event: threading.Event | None = None,
    ) -> CopilotResult:
        """Execute a Copilot request (Help Me Reply, Explain Context, or Suggest a Question)."""
        recent_segments = self.context_store.get_recent_snapshot(seconds=180.0, max_segments=30)
        recent_text = " ".join(s.text for s in recent_segments)

        effective_query = (user_query or "").strip()
        if not effective_query:
            if action_type == "help_me_reply":
                effective_query = self._detect_latest_question(recent_segments) or "What is a helpful short comment or answer on the ongoing topic?"
            elif action_type == "explain_context":
                effective_query = "Summarize the technical decision, consensus, and key blockers discussed."
            elif action_type == "suggest_question":
                effective_query = "What is a smart, constructive technical question the developer should ask next?"

        recent_ids = {s.id for s in recent_segments}
        older_relevant = self.context_store.search_relevant(
            query=effective_query + " " + recent_text[-120:],
            top_k=4,
            include_neighbors=True,
            exclude_ids=recent_ids,
        )

        all_transcript_segments = sorted(recent_segments + older_relevant, key=lambda s: s.id)
        doc_query = f"{effective_query} {' '.join(s.text for s in all_transcript_segments[-5:])}"
        retrieved_docs = self.knowledge_store.search(doc_query, top_k=4)

        prompt_transcript = MeetingContextStore.format_for_prompt(all_transcript_segments, unconfirmed_live_text)
        prompt_docs = KnowledgeStore.format_for_prompt(retrieved_docs)
        user_prompt = build_user_prompt(prompt_transcript, prompt_docs, action_type, effective_query)

        raw_stream_buffer: list[str] = []
        english_started = False
        english_finished = False

        def filtered_on_text(token: str) -> None:
            nonlocal english_started, english_finished
            if english_finished or not on_text:
                return

            raw_stream_buffer.append(token)
            accumulated = "".join(raw_stream_buffer)

            if not english_started:
                match = re.search(r"###\s*ENGLISH(?:\s+ANSWER)?\s*[\n:]*", accumulated, re.IGNORECASE)
                if match:
                    english_started = True
                    after = accumulated[match.end():]
                    if after:
                        next_header = re.search(r"\n?###", after)
                        if next_header:
                            english_finished = True
                            clean_part = after[:next_header.start()]
                            if clean_part:
                                on_text(clean_part)
                        else:
                            on_text(after)
                elif len(accumulated) > 100 and not accumulated.strip().startswith("#"):
                    english_started = True
                    on_text(accumulated)
                return

            next_header = re.search(r"\n?###", token)
            if next_header:
                english_finished = True
                clean_part = token[:next_header.start()]
                if clean_part:
                    on_text(clean_part)
                return

            on_text(token)

        raw_text, usage = self.client.stream_chat(
            system_prompt=SYSTEM_PROMPT,
            user_message=user_prompt,
            on_text=filtered_on_text,
            stop_event=stop_event,
        )

        english_ans, viet_meaning, evidence_lines, warnings = parse_copilot_response(raw_text)

        valid_segments = {f"T#{s.id}": s.text for s in all_transcript_segments}
        valid_docs = {d.chunk_id: f"{d.filename} > {d.heading}: {d.text[:90]}..." for d in retrieved_docs}
        cited_ids = extract_citations(raw_text)
        matched_citations, unverified_citations = match_citations(cited_ids, valid_segments, valid_docs)

        return CopilotResult(
            action_type=action_type,
            english_answer=english_ans,
            vietnamese_meaning=viet_meaning,
            evidence_citations=matched_citations,
            unverified_citations=unverified_citations,
            warnings=warnings,
            raw_response=raw_text,
            usage=usage,
            retrieved_segments=all_transcript_segments,
            retrieved_docs=retrieved_docs,
        )

    def _detect_latest_question(self, segments: list[TranscriptEntry]) -> str | None:
        """Scan backwards to find the most recent direct question in the transcript."""
        question_words = {"what", "how", "why", "when", "where", "who", "which", "can", "could", "should", "is", "are", "do", "does", "think"}
        for s in reversed(segments):
            if s.is_filler:
                continue
            text = s.text.strip()
            if text.endswith("?"):
                return text
            words = text.casefold().split()
            if words and words[0] in question_words and len(words) >= 4:
                return text
        return None

