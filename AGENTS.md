# Instructions for Codex & Copilot Development

## Current Phase: Hybrid Translation & Claude Meeting Copilot

The project integrates an on-demand, privacy-preserving **Meeting Copilot** alongside the local live translation pipeline:

1. **Local Live Translation Pipeline (Independent & Autonomous)**:
   - Captures system audio via BlackHole 2ch + Multi-Output Device.
   - Whisper Small.en (local MLX) + TranslateGemma 4B (local Ollama).
   - Low-latency Meeting Follow mode with prioritized streaming and selective reconciliation.
   - 100% offline-capable; never requires cloud APIs or internet during translation.

2. **Meeting Copilot (On-Demand Cloud Assistant)**:
   - In-memory `MeetingContextStore` capturing finalized English segments.
   - Local in-memory `KnowledgeStore` (SQLite FTS5) indexing user-selected Markdown and TXT documentation.
   - Remote `ClaudeClient` (Claude Haiku 5.5 via official `anthropic` SDK) invoked **strictly on explicit user action**.
   - Generates suggested English replies (1–3 short spoken sentences), Vietnamese translation, and matched source citations.
   - Strict privacy opt-in: checkbox is unchecked by default; transcripts and docs are never persisted to disk.

## Architectural & Coding Rules

- **Simple → Correct → Maintainable → Optimize when needed.**
- **File Size Constraint**: Each handwritten Python file must not exceed **200 physical lines** (see `SPEC_02_REFACTOR_MAX_200_LINES.md`). Split by single responsibility when approaching limits.
- **Entrypoints**:
  - `ui.py`: PySide6 bilingual desktop application (Live Translation + Meeting Copilot).
  - `main.py`: Shared audio/model helpers, device diagnostics, and optional legacy CLI tools.
- **Python Runtime**: Strictly Python 3.12 (`requires-python = ">=3.12,<3.13"`). Managed via `uv` with `uv.lock`.
- **Minimal Abstractions**: Readable Python, explicit type annotations, dataclasses, minimal inheritance. Preserve existing working logic where reasonable.
- **Privacy & Safety Invariants**:
  - Cloud opt-in checkbox defaults to `False`. Presence of an API key must never auto-enable cloud transmission.
  - Transcripts and indexed documents reside strictly in in-memory structures and are cleared on session reset.
  - Citations must be matched against retrieved IDs; do not claim semantic verification.
- **No unit tests unless explicitly requested**: Include clear manual smoke-check instructions.
- **Verification**: Run `uv run --locked python -m compileall -q .` and `git diff --check` before completing tasks. Never assert hardware runs were tested unless actually executed on macOS.

## Historical Note (Legacy MVP Scope)
*The initial MVP phase prohibited meeting memory and cloud APIs to focus on core audio routing and latency benchmarks. That milestone has been completed. Legacy CLI/TTS documents have been moved to `docs/legacy/`.*

## Reporting Format

Provide: **what changed**, **files modified**, **how to run on Mac**, **what was and was not verified**, **known limitations**, **next step**.
