# Mac Live Voice Translator — Product & Engineering Specification

**Status:** Handover to Codex; MVP scope only.  
**Target:** Apple Silicon MacBook **M1 Pro, 16 GB unified RAM**, macOS 14.2+ recommended for native tap phase.  
**Language:** Vietnamese. **Version:** 1.0 — 2026-11-04.  
**Engineering principle:** **Simple → Correct → Maintainable → Optimize when needed**.

> The user wants a universal macOS audio-translation layer and meeting copilot. When enabled, English speech played by YouTube, Google Meet, Zoom, or other software through the selected system audio path is captured locally, transcribed, translated to Vietnamese, and displayed progressively. An integrated on-demand Meeting Copilot leverages in-memory meeting context and local Markdown/TXT documentation to help the user speak natural English responses via Claude Haiku 5.5.

## 1. Product goal

**User story:** “I switch on a local Mac app, join an English-language technical meeting, follow Vietnamese live captions in real time, and when asked a question, click 'Help Me Reply' to get 1–3 clear English sentences grounded in our docs and transcript that I can immediately speak aloud.”

### In scope (Hybrid Architecture)

1. Capture system output audio routed to BlackHole 2ch without audio feedback.
2. Local English ASR via MLX Whisper Small.en.
3. Local English → Vietnamese translation via Ollama TranslateGemma 4B with prioritized scheduling.
4. Meeting Follow UI in PySide6 with Live Meeting Focus and dual transcript history.
5. In-memory `MeetingContextStore` (up to 1500 segments in bounded RAM).
6. Local `KnowledgeStore` indexing user-selected Markdown and TXT files using SQLite FTS5.
7. On-demand `ClaudeClient` (Claude Haiku 5.5) streaming short, spoken English responses and Vietnamese meaning.
8. Citations validated against actual retrieved segment and document IDs.
9. Strict privacy opt-in: transcripts are never saved to disk; Claude is contacted only on explicit user click.
10. Offline resilience: live translation functions 100% locally without internet or API keys.

### Historical MVP Scope (Archive Reference)
*(Early specification restricted meeting memory and cloud APIs during initial PortAudio loop validation; see sections below for initial audio routing specifications).*
- Native menu bar app, Core Audio Process Tap, automatic audio-device switching (later phase).
- Seamless translation of **all** sounds: music, notification sounds, sound effects, encrypted/protected playback, and unsupported audio routes are not semantically translatable. Initial replacement mode intentionally silences non-speech source audio.
- Zero-delay full-duplex simultaneous interpretation. There will be unavoidable capture, sentence-boundary, model and speech-generation latency.

## 2. Technical constraints and realism

- **Hardware:** M1 Pro / 16 GB unified memory; Chrome/Meet plus ASR plus translation model must fit in available RAM. No simultaneous large LLMs.
- **Audio replacement vs. capture are separate:** simply reading system audio doesn't remove English from the headphones. For MVP set **macOS default output to BlackHole 2ch**; separately play generated Vietnamese into the actual headphone device. **Do not use Multi-Output Device in replacement mode**, as that also plays the English original.
- **System audio scope:** This captures apps routed to the selected BlackHole output. Apps using a separately configured physical output might bypass it. Not a blanket guarantee for every audio source or protected media.
- **Meet:** Remote participants' audio is one mixed stream and can be translated, but overlapping voices hurt ASR; the user's own microphone isn't routed through this capture by default. TTS audio must never feed into the meeting microphone.
- **Offline:** model/voice installation requires one-time network access. Inference should stay on device; Ollama's HTTP endpoint must be `127.0.0.1` only. Validate that the app makes no calls to cloud APIs during a session.
- **Safety / consent:** Never record covertly. Observe employer, conference and participant-consent rules. Default must not save raw audio, transcript, or translations to disk.
- **Audio output failures:** if TTS or capture fails, clearly warn that normal audio may be muted until output is restored. Provide an easy STOP and help to restore. For native mute phase, design fail-open cleanup and recovery; never promise absolute crash-safe behavior without OS validation.

## 3. Chosen tech stack

| Layer | MVP | Later native option |
|---|---|---|
| Input capture | BlackHole 2ch + `sounddevice`/PortAudio | Swift Core Audio Process Tap (macOS 14.2+) |
| App control | Python 3.11/3.12 ARM64 CLI | SwiftUI menu bar shell + Python worker |
| Audio processing | NumPy + `scipy.signal.resample_poly` | Core Audio native buffers if needed |
| Speech activity detection | Start with fixed chunks; add light VAD next | ONNX Silero VAD if useful |
| Speech-to-text | `mlx-whisper`, model `mlx-community/whisper-small.en-mlx` | `whisper.cpp` fallback / alternate model |
| Translation | Ollama `translategemma:4b`, temperature 0 | Benchmark lightweight alternatives if throughput poor |
| TTS | macOS `say` voice `vi_*`, generate local PCM/AIFF | Local Vietnamese streaming TTS if required |
| Playback | `sounddevice.OutputStream` / explicit physical device | Native audio playback |
| Persistence | None (in-memory bounded buffers only) | Optional future opt-in persistence |

Notes:
- `translategemma:4b` Ollama distribution is ~3.3 GB on disk; Whisper small.en MLX repo is ~481 MB, not the complete RAM footprint. Memory/runtime usage must be measured on target hardware.
- Translation prompt should explicitly mention source English `en` and target Vietnamese `vi`; no markdown or explanatory output.
- macOS availability of a Vietnamese voice varies by installed voices and OS version: detect via `say -v ?`; provide a clear failure message when missing. Do not silently synthesize English with a non-Vietnamese voice.

## 4. End-to-end architecture

```text
Any app playing speech (Meet / Zoom / YouTube / Facebook / browser)
    │
    ▼
macOS System Output set to BlackHole 2ch   [original English not audible on physical headphones]
    │
    ▼
BlackHole INPUT → AudioCapture (48 kHz stereo PCM, callbacks only enqueue data)
    │
    ▼
Mono downmix + resample → 16 kHz PCM → Speech segmentation (fixed chunks in baseline; VAD in P2)
    │
    ▼
ASR worker: mlx-whisper, language=en
    │  English text
    ▼
Translation worker: local Ollama /api/chat → Vietnamese-only text
    │
    ▼
TTS worker: macOS Vietnamese voice → PCM
    │
    ▼
Physical headphones selected explicitly (never BlackHole / Multi-Output)
```

### Core behavioral requirements

**FR-01 — Source independent.** Changing between browser tabs and Google Meet requires no API integration; so long as app audio routes to BlackHole, the capture pipeline sees it.

**FR-02 — Speech-only best effort.** Do not attempt to translate music, effects, noise, or silence. Keep original muted in MVP; warn clearly of missing non-speech audio.

**FR-03 — Order.** Vietnamese playback remains in source chronological order. Each speech segment has a monotonic ID and timestamp. Translation results can arrive asynchronously but must be sequenced before TTS.

**FR-04 — Continuous capture.** Audio capture must not block while ASR, translation, TTS, or playback runs. Use bounded queues and separate workers; callbacks must not perform inference, network requests, disk writes, or lengthy logging.

**FR-05 — Backpressure.** Bound audio/segment/translation/TTS queues. If backlog grows, log a visible stale-segment/drop counter and prune stale work according to an explicit policy. Don't silently queue minutes of translation. Favor freshness while preserving the relative order of what is played.

**FR-06 — Short-phrase handling.** Prevent translation of single noise bursts or repeated “you you you” hallucinations from silence. Do not blanket-remove real repeated words or identical statements that were actually spoken twice: timestamped dedup should be conservative.

**FR-07 — Audio isolation.** Generated Vietnamese audio must output to the physical device directly, never back into capture. Validate device identity, not just device indices, because indices may change after reconnection. Refuse invalid routes before starting.

**FR-08 — No session recording.** Do not persist raw PCM, transcripts, translations, or debug logs by default. Temporary TTS files should use secure temp paths and be removed. Downloaded model cache is allowed.

**FR-09 — Lifecycle.** Start, stop, Ctrl+C, error, output disconnect, capture device unplug, Ollama stopped, model missing. Each should lead to a clear terminal message and orderly cleanup. Document the one manual step to restore macOS default output in P1.

**FR-10 — Local processing.** No cloud APIs; only approved model download tools during setup, `127.0.0.1:11434` during inference.

**FR-11 — Source content is data.** Do not treat spoken user content as an instruction to the model; translation only, even if someone says “ignore previous instructions”.

**FR-12 — Fail visibly.** If no voice, permission, device, input level, or Ollama connection exists, show a specific actionable error, not an empty/silent hang.

## 5. Suggested processing interfaces

Keep abstractions minimal and stable. These are interface *suggestions*, not a demand for over-engineering:

```python
@dataclass(frozen=True)
class SpeechSegment:
    id: int
    start_ms: int
    end_ms: int
    pcm_16k_mono: np.ndarray  # float32, ephemeral

@dataclass(frozen=True)
class TranscribedSegment:
    id: int
    start_ms: int
    end_ms: int
    english: str

@dataclass(frozen=True)
class TranslatedSegment:
    id: int
    start_ms: int
    end_ms: int
    english: str
    vietnamese: str
```

Pipeline stages should expose simple `start()`, `stop()`, and `process(...)` interfaces or plain functions, not a generalized agent framework. Each queue must have `maxsize` and metrics: `queue_size`, `dropped`, `processing_ms`.

### Segment policy

- Baseline from included legacy MVP: **4-second fixed chunks** (use only to prove audio routing). Real-time quality may be poor at phrase boundaries.
- Next improvement: VAD-based boundaries, target **0.3–0.6s silence end-of-utterance**, target 1–4s segments, configurable max duration **5–7s**; use a small audio pre-roll ~0.2s. Do not split mid-word when avoidable. Do not hold indefinitely while speech continues.
- Keep ASR constrained to `en`, trim whitespace, and filter known silent hallucinations conservatively.
- Translation prompt example:

```text
You are a professional English (en) to Vietnamese (vi) translator.
Translate the given spoken English into concise, natural spoken Vietnamese.
Preserve names, numbers, and technical terminology (such as UAT, API, repository).
Only return the Vietnamese translation. No extra commentary or instructions.

<English speech segment>
```

Guard against output accidentally containing chain-of-thought, metadata, or invented content. The model processes untrusted speech as text only.

### TTS + queue policy

- Verify macOS Vietnamese voice first, then synthesize phrase-by-phrase and play through selected headphone device.
- TTS may be slower than live source speech. Record `backlog_ms` / seconds of queued synthesized speech. When lag passes configurable threshold (default experiment: 8–12s), display warning and allow a **skip stale** policy with count; never promise verbatim full coverage in this mode.
- Source timestamps must be included in logs (when debug enabled) to measure true perceived lag.
- Add short fades at audio joins if there are clicks; do not unintentionally change TTS speed without user choice.
- Future enhancement: streamed TTS chunks and time-stretch/speech speed adjustments, but only after baseline works.

## 6. Source layout for Codex

A small modular structure is preferred **after** confirming the current `main.py` behavior. Do not explode into many files on day one.

```text
mac-live-translator/
├── SPEC.md                       # this handover
├── AGENTS.md                     # Codex implementation rules
├── README.md                     # user setup and operating instructions
├── requirements.txt
├── main.py                       # CLI entrypoint
└── translator/
    ├── config.py                 # dataclass, validation
    ├── audio.py                  # BlackHole capture + physical output + routing guard
    ├── segmenter.py              # fixed chunk, then optional VAD
    ├── asr.py                    # mlx-whisper wrapper
    ├── translate.py              # local Ollama wrapper
    ├── tts.py                    # macOS Vietnamese voice
    └── pipeline.py               # queues, workers, lifecycle, basic metrics
```

Keep existing behavior before restructuring. No plugin system, database, web server, Docker, or Rust required for MVP.

## 7. Concrete execution milestones

### P0 — Audit + audio I/O proof (must complete first)

1. Read **all** files of the existing starter (`main.py`, `requirements.txt`, `README_LEGACY_MVP.md`); summarize current implementation and gaps before modifying.
2. Confirm target Mac OS version, Python `arm64`, available devices, and microphone/virtual-device input permission as needed.
3. Implement/confirm CLI `--list-devices`, `--list-voices`, `--test-voice`, `--monitor-input` (RMS/peak without recording or ASR), `--output-device`.
4. Ensure BlackHole is the actual macOS system **output**, while TTS output is physical headphones; show explicit fail-fast safety guard against feedback.
5. Manual smoke check with a YouTube English clip: audio level > silence while the source English is not audible on headphones; Vietnamese TTS voice probe works through headphones.
6. Show unambiguous STOP and restore-system-output instructions.

**Acceptance:** A user can distinguish BlackHole source from physical headphone output; test voice plays to physical headphones with no loop and YouTube audio is captured. No ASR/translation is necessary to pass P0.

### P1 — Functioning end-to-end English → Vietnamese speech MVP

1. ASR: use model `mlx-community/whisper-small.en-mlx`; short chunks initially.
2. Translator: local Ollama `translategemma:4b`; proper prompt and localhost timeout/error handling.
3. TTS: Vietnamese `say` voice, decode synthesized audio and play to selected output.
4. Display `EN:` and `VI:` diagnostic lines with elapsed timing; **terminal output is temporary**, no file saves.
5. Separate audio capture worker, inference/translate worker(s), and TTS worker(s), with bounded buffers. Capture must continue during TTS.
6. Provide local model warming, device configuration, stop/shutdown cleanup, and simple session health info.
7. Avoid a brittle all-in-one synchronous loop; refactor only as much as needed to separate blocking tasks.

**Acceptance:** On an English YouTube talk and a Google Meet demo with multiple participants (not necessarily speaking simultaneously), the user hears intelligible Vietnamese via physical headphones, not the original English. Show measured lag rather than claiming an arbitrary result. No cloud calls and no recordings.

### P2 — Reduce lag and improve robustness

1. Introduce VAD-based speech segmentation; measure latency vs fixed 4s chunks, keep rollback switch.
2. Add per-stage metrics: capture-to-segment-final, ASR, translate, TTS-first-audio, playback complete, end-to-end lag, queue depth, dropped segments.
3. Tune chunk thresholds and model concurrency on M1 Pro 16GB. Keep only one translation model resident.
4. Protect against silent hallucinations, duplicate segments, long or overlapping speech, Bluetooth reconnect, Ollama errors and stalled outputs.
5. Add mode to **fallback to pass-through / prompt manual audio restoration** when translation fails; implementation must be safe and explicit, not invisible loss of system sound.
6. Optionally benchmark `whisper-base.en` if small.en is too slow; select by real measured quality/latency trade-off.

**Target, not guarantee:** Aim for noticeable first Vietnamese playback about **3–6 seconds** after an English speech segment becomes available, with transparent p50/p95 measures. Long sentences, TTS speaking duration and overload will increase lag. Record results from the actual target Mac; never claim “real-time zero latency.”

### P3 — Native app (NOT authorized until P0–P2 are stable)

1. Swift macOS menu bar app: ON/OFF, output device, status, quick STOP, audio level, selected mode.
2. Replace BlackHole with **Core Audio Process Tap** + aggregate device; test capture without changing system output first.
3. Explicitly design **source muting** vs TTS output routing, self-process exclusion/loop prevention, permissions, and restore behavior. Apple documents tap muting; test with Chrome, Meet, Zoom, built-in and Bluetooth audio.
4. Include `NSAudioCaptureUsageDescription` Info.plist key and macOS System Audio Recording permission workflow.
5. Handle app process + worker process PIDs when excluding TTS from global process capture; do not assume excluding only Swift host process also excludes Python child.
6. Only after validating native path: make switching ON activate tap/mute and OFF restore original playback; no silent stuck state when process crashes.

**Acceptance:** App ON starts translation; OFF restores original audio; source never loops TTS into ASR; macOS privacy requests are clear; no BlackHole dependency on supported native platform (if feasible after empirical verification).

## 8. CLI / runtime UX requirements

Initial commands (exact names can reflect existing CLI):

```bash
# Install BlackHole via Homebrew (manual permissions/system settings remain necessary)
brew install blackhole-2ch ffmpeg

# Install models and voice assets (first-time internet connection)
ollama pull translategemma:4b

# From project folder, after arm64 Python virtualenv and requirements install
python main.py --list-devices
python main.py --list-voices
python main.py --monitor-input --input-device "BlackHole 2ch"
python main.py --test-voice --output-device <physical-headphone-id>
python main.py --output-device <physical-headphone-id>
```

In P1, show a startup summary: physical output name; input name; Whisper model; translator model; selected VI voice; replacement routing reminder; Ctrl+C restore note. Error messages must be understandable to a non-audio developer.

## 9. Acceptance checklist (manual QA, no unit tests requested)

**Correctness**
- [ ] Physical device test speaks Vietnamese audibly; no feedback.
- [ ] Clear English YouTube speech yields intelligible spoken Vietnamese.
- [ ] Facebook browser video works when its playback uses system default output.
- [ ] Google Meet with 5 participants works for remote speech when speakers take turns.
- [ ] English source cannot also be heard in replacement mode through the same physical headphones.
- [ ] Speech from app does not leak into its input stream or conference microphone.
- [ ] Stopping CLI ends audio work and prints how to restore normal macOS output.

**Performance & stability**
- [ ] 15-minute continuous session without runaway queues or uncontrollable lag.
- [ ] Timings and dropped-count visible; no hardcoded “2 seconds” guarantee.
- [ ] M1 Pro 16GB remains responsive with Chrome and Meet; report Activity Monitor memory pressure / swap and CPU/GPU utilization.
- [ ] Mic remains usable in Meet; app does not hijack user's recording input.
- [ ] Bluetooth device disconnect/reconnect results in visible alert/recovery instructions.

**Privacy**
- [ ] Session audio/transcript/translation not persisted by default.
- [ ] No remote inference or analytics/network telemetry.
- [ ] System permissions and call-recording consent documented.

## 10. Known problems in the included starter code (avoid perpetuating them)

The included `main.py` is an **unverified exploratory prototype**, not a validated production implementation. Preserve useful code, but review:

1. **Fixed chunks** split sentences and add large latency; P2 requires VAD-based segmentation.
2. **Serial ASR → translate** work in a loop may not keep up with active calls; use bounded queues, timestamps, and data flow so capture remains continuous.
3. **TTS is phrase-level synchronous**, and playback duration may exceed generation interval. Queues need explicit stale-policy visibility.
4. **Audio backend device indices** are unstable across changing devices; validate by name/UID and capabilities, not number alone.
5. **No fully automated audio restoration** in BlackHole routing; don't present MVP as an always-safe one-click app.
6. **`--test-voice` should not require a valid BlackHole input** if it is testing only output; fix CLI validation order.
7. **Per-app audio routes** might bypass macOS default system output. Provide a clear troubleshooting path instead of claiming all apps always work.
8. **No native process tap, menu bar, or latency benchmark** is currently implemented.
9. **Audio capture callback logging and errors** must not create real-time thread stalls; perform diagnostics on a consumer thread.
10. **Chunk RMS threshold** is not speech detection, and can trigger ASR on music/noise; optional VAD later.

## 11. Development & review rules for Codex

1. **Simple → Correct → Maintainable → Optimize when needed.** Minimal abstractions, readable code, preserve existing working behavior.
2. **Do not add unit tests unless specifically requested by the user.** Do provide clear manual smoke-check instructions and expected outputs.
3. Make one milestone at a time; complete P0 then P1 before considering native work.
4. Explain design tradeoffs and why a change is necessary. Prefer exact, file-by-file changes over generic high-level advice.
5. Validate sample rates, input/output selection, model existence, and network target before allocating heavy resources.
6. Never introduce cloud service, file persistence, meeting recording, auto-sharing, or backend without user approval.
7. Do not assert hardware test results you cannot measure. If running outside macOS, explain what requires validation on the user's Mac.
8. On completion of each milestone, report: files changed, commands to run, expected output, known risks, and concrete next steps.

## 12. Reference docs / source-of-truth

- Apple Core Audio taps, muting & macOS 14.2+: https://developer.apple.com/documentation/coreaudio/capturing-system-audio-with-core-audio-taps
- ScreenCaptureKit docs and process audio exclusion: https://developer.apple.com/documentation/screencapturekit/scstreamconfiguration/excludescurrentprocessaudio
- BlackHole audio routing: https://github.com/ExistentialAudio/BlackHole
- Whisper Apple Silicon alternatives: https://github.com/ggml-org/whisper.cpp ; https://mlx-framework.org/
- MLX Whisper small.en model: https://huggingface.co/mlx-community/whisper-small.en-mlx
- TranslateGemma prompts and Ollama model tags: https://ollama.com/library/translategemma
- macOS voice setup: https://support.apple.com/guide/mac-help/change-the-voice-your-mac-uses-to-speak-text-mchlp2290/mac
- Silero VAD (optional P2): https://github.com/snakers4/silero-vad

## 13. Definition of Done (first deliverable)

Do **not** claim the complete app is done just because models return text. The first deliverable (P0 + P1) is done only if, on the user's M1 Pro 16 GB:

- English speech from a YouTube clip is captured via BlackHole.
- Whisper returns understandable English transcript.
- Local TranslateGemma returns Vietnamese translation.
- A Vietnamese TTS voice is clearly audible in the physical headphones while original English is not.
- Playback does not loop into capture.
- Stop, unavailable devices/models, and audio recovery are documented.
- No meeting context, database, or LLM answer assistant exists in this deliverable.

**User priority:** Make the English-audio-to-Vietnamese-headphones loop useful **first**; only then improve latency, UX, and native macOS integration.
