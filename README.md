# Mac Live Translator & Meeting Copilot — live English to Vietnamese text

Local desktop workspace for Apple Silicon macOS. System audio goes through a **Multi-Output Device** containing BlackHole 2ch and your headphones. You continue hearing the original English. The app reads BlackHole, runs cached MLX Whisper and local Ollama TranslateGemma, and shows progressive real-time bilingual text. It does not save audio or transcripts to disk.

---

## 1. Install

```bash
brew install uv ffmpeg ollama
brew install --cask blackhole-2ch
brew services start ollama
ollama pull translategemma:4b
uv sync --locked
uv run --locked python -c 'from huggingface_hub import snapshot_download; snapshot_download("mlx-community/whisper-small.en-mlx")'
```

First setup needs internet. During a session, Whisper uses cached model files and Ollama is contacted only at `127.0.0.1:11434`. Dependencies live in `pyproject.toml` and `uv.lock`; there is no pip/requirements workflow.

---

## 2. Route audio

In **Audio MIDI Setup**, create a Multi-Output Device containing **BlackHole 2ch** and your physical headphones. Select it in **System Settings > Sound > Output**. Check that English remains audible in the headphones. In Meet/Zoom, keep your real microphone selected and use the macOS default output. The app refuses text capture if the default output is not named Multi-Output Device. It cannot inspect member devices, so verify them in Audio MIDI Setup.

---

## 3. Unified Desktop Workspace (No Tab Switching)

The redesigned PySide6 desktop interface combines live translation and on-demand AI assistance into a **single, unified macOS dark workspace**:

### Left Panel: Live Translation (Trực tiếp) (~55%)
- **Recent Context**: Displays the ongoing discussion topic grounded in recent segments.
- **Hero Live Vietnamese Subtitles**: Real-time streaming translation with high-contrast text and draft-to-final indicators.
- **Live English Transcript**: Immediate ASR text from MLX Whisper Small.en.
- **Live Metrics Strip**: Active listening status, first-token latency, final translation latency, and queue backlog.
- **Transcript History**: Scrollable history with quick toggles (`VI - Bản dịch` / `EN - Transcript`).

### Right Panel: Meeting Copilot (Trợ lý cuộc họp) (~45%)
- **Quick Question Input**: Ask questions or provide custom focus (overrides automatic question detection).
- **Smart Question Detection**: Deterministic multi-segment reconstruction for fragmented ASR speech (e.g. `What do you think` + `Sydney?`).
- **One-Click Actions**:
  - **Help Me Reply** (Primary): Generates 1–3 short, spoken English sentences grounded in context.
  - **Explain Context**: Summarizes technical consensus, decisions, and blockers.
  - **Suggest Question**: Formulates constructive technical questions to ask next.
  - **Hủy (Cancel)**: Promptly terminates in-flight Claude requests.
- **Hero Spoken Reply**: Streamed spoken English text ready to be read aloud, with a one-click **Sao chép** (Copy) button.
- **Vietnamese Meaning & Evidence**: Side-by-side translation of the reply and verified source citations (`[T#id]`, `[DOC#id]`).
- **Knowledge & Context Chips**: Interactive chips to manage local Markdown/TXT documentation (SQLite FTS5) and review/clear meeting transcripts.
- **Source Preview & Privacy**: "Xem trước ngữ cảnh" displays the exact immutable prompt and excerpts before transmission. Cloud opt-in remains disabled by default.

---

## 4. How to Run on Mac

### Launch Redesigned Desktop App:
```bash
uv run --locked python ui.py
```

### List Detected Audio Devices:
```bash
uv run --locked python main.py --list-devices
```

### Verify Compilation:
```bash
uv run --locked python -m compileall -q mac_live_translator
```

---

## 5. Manual checks

1. Confirm `--list-devices` shows BlackHole and the headphones, and the system default output is the Multi-Output Device.
2. Play a clear English YouTube talk. Confirm the original stays audible, and provisional English appears before a finalized line.
3. Confirm each final English line is added once, and Vietnamese grows token by token without duplicate history lines.
4. Observe the UI's first English, first Vietnamese token, and final Vietnamese lag values. Test Stop during translation.
5. Try a meeting with speakers taking turns; watch memory pressure on the 16 GB Mac and note dropped-work warnings.

Speech detection uses a light RMS threshold, not a trained VAD; music and noise can still trigger Whisper. Provisional decodes need at least 0.45 s of new audio and are spaced at least 0.75 s apart. There is no artificial 200 ms stability timer: stability requires two Whisper hypotheses. The final pass reuses the latest provisional result when no new speech arrived. Capture uses 20 ms blocks and an eight-second bounded buffer; an overload drops old audio and visibly cancels the current draft. The translation queue is bounded and the app stops with an error if it fills rather than silently omitting speech. Overlapping windows cost compute and may revise provisional text. Fragmented Vietnamese may have awkward word order; review the final lines for accuracy. Model speed and actual lag must be measured on the target Mac. Bluetooth reconnects can change device indices. Nothing is persisted by this app, but Terminal output can be saved if you redirect it.

---

## 6. Five-minute YouTube benchmark

1. Connect the same headphones, use the same Multi-Output route, close other heavy applications, and run `uv run --locked python ui.py` in Terminal. Keep Whisper Small.en and TranslateGemma 4B unchanged. Wait for **Listening** so both models are warm.
2. Open [the benchmark clip at 176 seconds](https://www.youtube.com/watch?v=Wb8dxOUDtCs&t=176s). Keep playback at 1× and the same volume; do not pause or seek during the five-minute interval.
3. Press **Start**, then play exactly five minutes. Press **Stop** after the clip. Confirm the UI shows provisional English, finalized English, and progressively updated Vietnamese without duplicate final lines. Note any dropped-work status and Activity Monitor memory pressure.
4. Read Terminal's `METRIC` lines and final `BENCHMARK` line. The latter reports count plus p50/p95 for audio-to-first-English, audio-to-first-visible-Vietnamese, and audio-to-final-Vietnamese. `TRACE`, `COVERAGE`, `REVISION`, `SKIPPED`, and `OLLAMA` show fragment wait, request timing, English words submitted, corrections, omitted work, and model load. No transcript or audio is written to disk by the app.
5. Repeat the same clip with the previous revision if it is available, using the same route and model state. Compare p50/p95, completed line count, words covered, revisions, and missed or repeated clauses, negation, numbers, and IT terms. Note any interruption or model reload. A lower latency with missing or inaccurate lines is not an improvement.

The source timestamp is the estimated ADC time of the first captured block above the speech threshold, mapped to `time.monotonic()`. It is not the YouTube player's presentation timestamp or the exact first phoneme. The earlier 3.3 s first-token and 3.9 s final figures began at callback receipt, so they are **historical reference values**, not directly comparable to these new measurements. Rerun a baseline with the same timestamp definition before claiming a measured speedup. Long speech, punctuation pauses, and the seven-second hard limit change what counts as an utterance; compare transcript quality alongside latency.

The prior run reported audio-to-first-EN about 1.39 s and audio-to-first-VI about 7.61 s. These are historical observations; this fragment-based revision has not yet been measured on that clip. `TRACE` reports source-audio-to-first-EN, stable English, fragment eligibility, final EN, queue wait, Ollama request start, first token received, and first token rendered. `OLLAMA` reports model load, prompt and generation duration from the local server. A small load duration supports that the warmed model stayed resident. Do not attribute the older 6.20-second gap to a specific stage without a comparable traced run.

### Scheduling comparison on the M1 Pro (2026-11-04)

| Run from 176 s | Completed lines | First EN p50 / p95 | First VI p50 / p95 | Final VI p50 / p95 |
|---|---:|---:|---:|---:|
| Previous 1.1 s decode / 8-word early threshold | 42 | 1.416 / 1.860 s | 5.846 / 7.657 s | 8.739 / 9.498 s |
| 0.75 s decode / 5-word early threshold | 34 | 1.035 / 1.759 s | 3.882 / 5.743 s | 8.656 / 9.124 s |

Both runs used the same YouTube URL and 176 s start point, warmed Whisper Small.en and TranslateGemma 4B, and the same BlackHole/Multi-Output route. The second playback paused once, so its 34-line count and p50/p95 are **indicative**, not a controlled five-minute quality comparison. The faster first-VI result is consistent with the per-line traces: queue wait was usually 0, Ollama load was usually a few milliseconds, and the translation eligibility timestamp moved earlier. The <3 s first-VI target occurred for some short or early-stable phrases; it was not the median. Repeat an uninterrupted run before declaring a final performance target met.
