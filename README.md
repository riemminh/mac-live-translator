# Mac Live Translator — live English to Vietnamese text

Local desktop prototype for Apple Silicon macOS. System audio goes through a **Multi-Output Device** containing BlackHole 2ch and your headphones. You continue hearing the original English. The app reads BlackHole, runs cached MLX Whisper and local Ollama TranslateGemma, and shows progressive text. It does not save audio or transcripts.

## Install

```bash
brew install uv ffmpeg ollama
brew install --cask blackhole-2ch
brew services start ollama
ollama pull translategemma:4b
uv sync --locked
uv run --locked python -c 'from huggingface_hub import snapshot_download; snapshot_download("mlx-community/whisper-small.en-mlx")'
```

First setup needs internet. During a session, Whisper uses cached model files and Ollama is contacted only at `127.0.0.1:11434`. Dependencies live in `pyproject.toml` and `uv.lock`; there is no pip/requirements workflow.

## Route audio

In **Audio MIDI Setup**, create a Multi-Output Device containing **BlackHole 2ch** and your physical headphones. Select it in **System Settings > Sound > Output**. Check that English remains audible in the headphones. In Meet/Zoom, keep your real microphone selected and use the macOS default output. The app refuses text capture if the default output is not named Multi-Output Device. It cannot inspect member devices, so verify them in Audio MIDI Setup.

```bash
uv run --locked python main.py --list-devices
uv run --locked python ui.py
```

Choose BlackHole capture and your headphone output, then press **Start**. The UI does not play TTS. An English live line changes as overlapping Whisper windows decode; repeated words seen in consecutive windows are marked stable. A speech pause or a seven-second limit finalizes a line. Only finalized English is submitted to Ollama, whose Vietnamese output appears progressively. **Stop** ends capture; restore your normal macOS output manually when done.

The legacy spoken mode remains optional: `uv run --locked python main.py --speak --output-device "Your headphones"`. It requires macOS output set to BlackHole 2ch and an installed Vietnamese voice. Do not use a Multi-Output Device for spoken replacement mode.

## Manual checks

1. Confirm `--list-devices` shows BlackHole and the headphones, and the system default output is the Multi-Output Device.
2. Play a clear English YouTube talk. Confirm the original stays audible, and provisional English appears before a finalized line.
3. Confirm each final English line is added once, and Vietnamese grows token by token without duplicate history lines.
4. Observe the UI's first English, first Vietnamese token, and final Vietnamese lag values. Test Stop during translation.
5. Try a meeting with speakers taking turns; watch memory pressure on the 16 GB Mac and note dropped-work warnings.

Speech detection uses a light RMS threshold, not a trained VAD; music and noise can still trigger Whisper. Provisional decodes require at least 0.7 s of new audio and are spaced at least 1.1 s apart. The final pass reuses the latest provisional result when no new speech arrived. Capture uses 20 ms blocks and an eight-second bounded buffer; an overload drops old audio and resets the current provisional line. Overlapping windows cost compute and may revise provisional text. Model speed and actual lag must be measured on the target Mac. Bluetooth reconnects can change device indices. Nothing is persisted by this app, but Terminal output can be saved if you redirect it.

## Five-minute YouTube benchmark

1. Connect the same headphones, use the same Multi-Output route, close other heavy applications, and run `uv run --locked python ui.py` in Terminal. Keep the Whisper and Ollama models unchanged. Let model warming finish before timing.
2. Pick one five-minute English talk with mostly one speaker. Record its URL and exact start time for repeat runs. Set the same volume and do not pause or seek during a run.
3. Press **Start**, then play exactly five minutes. Press **Stop** after the clip. Confirm the UI shows provisional English, finalized English, and progressively updated Vietnamese without duplicate final lines. Note any dropped-work status and Activity Monitor memory pressure.
4. Read the Terminal's `METRIC` lines and final `BENCHMARK` line. The latter reports count plus p50/p95 for audio-to-first-English, audio-to-first-visible-Vietnamese, and audio-to-final-Vietnamese. No transcript or audio is written to disk by the app.
5. Repeat the same clip once, using the same route and model state. Compare p50/p95 and the number of completed translations. A lower latency with many dropped or inaccurate lines is not an improvement.

The source timestamp is the estimated ADC time of the first captured block above the speech threshold, mapped to `time.monotonic()`. It is not the YouTube player's presentation timestamp or the exact first phoneme. The earlier 3.3 s first-token and 3.9 s final figures began at callback receipt, so they are **historical reference values**, not directly comparable to these new measurements. Rerun a baseline with the same timestamp definition before claiming a measured speedup. Long speech, punctuation pauses, and the seven-second hard limit change what counts as an utterance; compare transcript quality alongside latency.

For the current scheduling comparison, use [the owner's clip at 176 seconds](https://www.youtube.com/watch?v=Wb8dxOUDtCs&t=176s). The prior run reported audio-to-first-EN about 1.39 s and audio-to-first-VI about 7.61 s. Start at 176 seconds, play five minutes, and compare the new `METRIC` and `BENCHMARK` lines. Each `TRACE` line gives source-audio-to-first-EN-ready, first stable English, early translation eligibility, final EN, queue wait, Ollama request start, first token received, and first token rendered. `OLLAMA` lines show model load, prompt and generation duration reported by the local server. A small load duration confirms that the same warmed model remained resident. Do not interpret the older 6.20-second gap as a measured finalization or queue cost until a traced run attributes it.

### Scheduling comparison on the M1 Pro (2026-11-04)

| Run from 176 s | Completed lines | First EN p50 / p95 | First VI p50 / p95 | Final VI p50 / p95 |
|---|---:|---:|---:|---:|
| Previous 1.1 s decode / 8-word early threshold | 42 | 1.416 / 1.860 s | 5.846 / 7.657 s | 8.739 / 9.498 s |
| 0.75 s decode / 5-word early threshold | 34 | 1.035 / 1.759 s | 3.882 / 5.743 s | 8.656 / 9.124 s |

Both runs used the same YouTube URL and 176 s start point, warmed Whisper Small.en and TranslateGemma 4B, and the same BlackHole/Multi-Output route. The second playback paused once, so its 34-line count and p50/p95 are **indicative**, not a controlled five-minute quality comparison. The faster first-VI result is consistent with the per-line traces: queue wait was usually 0, Ollama load was usually a few milliseconds, and the translation eligibility timestamp moved earlier. The <3 s first-VI target occurred for some short or early-stable phrases; it was not the median. Repeat an uninterrupted run before declaring a final performance target met.
