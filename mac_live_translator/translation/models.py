"""Dataclasses representing translation fragments and speech segments."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(eq=False)
class Fragment:
    """An incremental unit of English speech queued or translated into Vietnamese."""
    id: int
    english: list[str]
    context: str
    queued_at: float
    vietnamese: str = ""
    status: str = "queued"
    dequeued_at: float = 0.0
    request_start_at: float = 0.0
    first_token_at: float = 0.0
    done_at: float = 0.0


@dataclass
class Segment:
    """A full speech utterance tracked across progressive ASR hypotheses."""
    id: int
    started: float
    previous: str = ""
    previous_at: float = 0.0
    stable: str = ""
    stable_since: float = 0.0
    fragments: list[Fragment] = field(default_factory=list)
    final_english: str | None = None
    revision: int = 0
    corrections: int = 0
    first_en_at: float | None = None
    stable_en_at: float | None = None
    first_vi_token_received_at: float | None = None
    first_vi_token_rendered_at: float | None = None
    final_vi_rendered_at: float | None = None
    finished: bool = False
    reconciled: bool = False
    is_filler: bool = False

