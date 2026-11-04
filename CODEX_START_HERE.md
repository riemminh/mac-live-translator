# Paste this as the first message to Codex

I want you to continue an existing local macOS voice translator project. My machine is an **Apple M1 Pro MacBook with 16 GB RAM**. The goal is to hear **Vietnamese spoken translation through my headphones** from English audio played by **any app routed to macOS output**, including YouTube, Facebook and Google Meet. This is **not primarily a subtitle app**. Do not add meeting memory, context databases, or AI answers.

Read `SPEC.md`, `AGENTS.md`, `main.py`, `requirements.txt`, and `README_LEGACY_MVP.md` first. The current Python source is a **prototype**, not hardware-verified. Implement **P0 and P1 only** in the order in the spec, retaining BlackHole for input routing and physical headphones as exclusive translation output. Prefer Python 3.11/3.12, MLX Whisper small.en, local Ollama TranslateGemma 4B, and macOS Vietnamese TTS. Preserve local-only inference, avoid any TTS feedback loop, and use bounded queues so processing does not block audio capture. Make STOP and audio recovery clear.

First, report a short audit of the existing starter and a minimal file-by-file implementation plan; then make the changes. Do not introduce unnecessary abstractions or unit tests unless I ask. Provide setup commands and manual checks I can run on my Mac. Explicitly state what you could not actually test in your environment.
