"""Event name definitions and callback type signatures."""

from __future__ import annotations

from typing import Any, Callable

# Pipeline lifecycle events
EVENT_STATUS = "status"
EVENT_STOPPED = "stopped"
EVENT_HEALTH = "health"

# ASR & Transcript events
EVENT_ENGLISH_PARTIAL = "english_partial"
EVENT_ENGLISH_FINAL = "english_final"

# Translation & Subtitle events
EVENT_VIETNAMESE_PARTIAL = "vietnamese_partial"
EVENT_VIETNAMESE_FINAL = "vietnamese_final"
EVENT_REVISION = "translation_revision"
EVENT_CANCELLED = "vietnamese_cancelled"
EVENT_TRANSLATION_DELAYED = "translation_delayed"
EVENT_TRANSLATION_SKIPPED = "translation_skipped"

# Metrics & Benchmark events
EVENT_TRACE = "trace"
EVENT_COVERAGE = "coverage"
EVENT_COVERAGE_FINAL = "coverage_final"
EVENT_OLLAMA_STATS = "ollama_stats"

# Type alias for event posting
EventCallback = Callable[[str, dict[str, Any]], None]

