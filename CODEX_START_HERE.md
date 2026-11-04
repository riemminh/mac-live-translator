# Project Overview: Mac Live Voice Translator & Meeting Copilot

My machine is an **Apple M1 Pro MacBook with 16 GB RAM**. The application provides:
1. **Live Meeting Translation**: Captures English audio via BlackHole 2ch, transcribes with local MLX Whisper Small.en, translates to Vietnamese with local Ollama TranslateGemma 4B, and displays prioritized meeting follow subtitles.
2. **Claude Meeting Copilot**: On-demand assistant using local context snapshots and SQLite FTS5 documentation retrieval to help formulate concise, spoken English replies via Claude Haiku 5.5.

Local translation operates 100% offline. Cloud assistance requires user opt-in and an Anthropic API key, invoked strictly when the user clicks Copilot actions.

Read `SPEC.md`, `AGENTS.md`, `ui.py`, `live_pipeline.py`, `meeting_context.py`, `knowledge_store.py`, `claude_client.py`, and `meeting_assistant.py`. Follow Simple → Correct → Maintainable → Optimize when needed.

*(Historical note: Early MVP instructions restricted memory/cloud APIs during initial audio-loop stabilization; that phase is complete and the hybrid Copilot is now authorized).*
