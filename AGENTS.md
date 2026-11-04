# Instructions for Codex

Start by reading `SPEC.md` fully and inspecting `main.py`, `requirements.txt`, and `README_LEGACY_MVP.md`.

Your current task is **P0 then P1 only**. Do **not** implement meeting memory, answer suggestions, speaker ID, context databases, a general agent, a web API, or a native SwiftUI app in this first increment. A CLI prototype that works reliably on the owner's **M1 Pro / 16GB** is the deliverable.

## Coding principles

- **Simple → Correct → Maintainable → Optimize when needed.**
- Minimal abstractions. Readable Python. Preserve existing working logic where reasonable.
- Validate configs, device selection, audio feedback safeguards, resources and failure paths.
- No unit tests unless the user explicitly asks; include manual smoke-check instructions.
- Write file-by-file concrete changes and explain why.
- Never assert that a hardware run was tested unless it actually ran on macOS.
- Offline inference after local setup. Do not upload audio, save transcripts or use cloud APIs.

## Exact work sequence

1. Audit starter files and identify actual bugs/risk areas.
2. Fix CLI/device checks, implement `--monitor-input` and reliable `--test-voice` if needed.
3. Confirm deterministic BlackHole input → physical-headphone output routing and no feedback.
4. Make ASR → local translation → Vietnamese TTS work with bounded queues.
5. Document M1 Pro installation/permissions, normal operation, failure/recovery, measurable latency, and manual QA.
6. Stop and report results and blockers. Do not jump to P2/P3 without owner approval.

## Reporting format

Provide: **what changed**, **files modified**, **how to run on Mac**, **what was and was not verified**, **known limitations**, **next step**.
