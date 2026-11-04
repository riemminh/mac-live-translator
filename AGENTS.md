# Instructions for Codex & Copilot Development

## Current Phase: Hybrid Translation & Claude Meeting Copilot

The project scope has been expanded by the owner to include an on-demand, privacy-preserving **Meeting Copilot** alongside the local live translation pipeline:

1. **Local Live Translation Pipeline (Independent & Autonomous)**:
   - Captures system audio via BlackHole 2ch.
   - Whisper Small.en (local MLX) + TranslateGemma 4B (local Ollama).
   - Low-latency Meeting Follow mode with prioritized streaming and selective reconciliation.
   - 100% offline-capable; never requires cloud APIs or internet during translation.

2. **Meeting Copilot (On-Demand Cloud Assistant)**:
   - In-memory `MeetingContextStore` capturing finalized English segments.
   - Local in-memory `KnowledgeStore` (SQLite FTS5) indexing user-selected Markdown and TXT documentation.
   - Remote `ClaudeClient` (Claude Haiku 5.5 via Anthropic API) invoked **strictly on explicit user action**.
   - Generates suggested English replies (1–3 short spoken sentences), Vietnamese translation, and citations.
   - Strict privacy opt-in: no automatic cloud uploads, transcripts never persisted to disk.

## Coding principles

- **Simple → Correct → Maintainable → Optimize when needed.**
- Minimal abstractions. Readable Python. Preserve existing working logic where reasonable.
- Validate configs, device selection, audio feedback safeguards, resources and failure paths.
- No unit tests unless the user explicitly asks; include manual smoke-check instructions.
- Write file-by-file concrete changes and explain why.
- Never assert that a hardware run was tested unless it actually ran on macOS.
- Local inference remains operational without cloud credentials or internet connectivity.

## Historical Note (Legacy MVP Scope)
*The initial MVP phase prohibited meeting memory and cloud APIs to focus on core audio routing and latency benchmarks. That milestone has been completed, and the current phase integrates the hybrid Meeting Copilot while preserving all previous audio safety and performance invariants.*

## Reporting format

Provide: **what changed**, **files modified**, **how to run on Mac**, **what was and was not verified**, **known limitations**, **next step**.
