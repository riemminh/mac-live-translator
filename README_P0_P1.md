# P0/P1: local English audio to Vietnamese headphones

This is a CLI prototype for an M1 Pro with 16 GB RAM. It captures apps using the **macOS default output** through BlackHole 2ch and plays Vietnamese speech to one explicitly selected physical headphone output. Original English is inaudible on those headphones only when macOS output is set to **BlackHole 2ch** and no app overrides that route. Music and effects are also muted. Do not create or select a Multi-Output Device.

## Install once, while online

```bash
brew install uv python@3.12 ffmpeg ollama
brew install --cask blackhole-2ch
brew services start ollama
ollama pull translategemma:4b
cd /Users/collins/Downloads/mac-live-voice-translator-m1pro
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -c 'from huggingface_hub import snapshot_download; snapshot_download("mlx-community/whisper-small.en-mlx")'
```

Run `uv venv` only when creating a new environment: it replaces an existing `.venv`. If `.venv` already uses Python 3.11 or 3.12, keep it and run only the `uv pip install` command. Restart the Mac after installing BlackHole if it does not appear in Sound settings. Install a Vietnamese macOS voice in **System Settings > Accessibility > Spoken Content / Read & Speak > System Voice** (the menu name varies by macOS release). Download voice assets while online. Verify `.venv/bin/python -c 'import platform; print(platform.machine())'` prints `arm64`, and `.venv/bin/python --version` is 3.11 or 3.12.

The Python program uses cached Whisper files only, macOS `say`, and Ollama at `127.0.0.1:11434`. Model/voice/package downloads are the one-time online setup. Session audio and text are held in memory and printed to Terminal; nothing is saved by the program except transient `say` audio in a deleted temporary directory. Avoid redirecting Terminal output to a file if you do not want a transcript.

## P0: prove the audio route

Connect **headphones**. In System Settings > Sound > Output, note their name, then select **BlackHole 2ch**. Check the browser/meeting app uses the system default output. Keep your real microphone selected separately in Meet/Zoom.

```bash
.venv/bin/python main.py --list-devices
.venv/bin/python main.py --list-voices
.venv/bin/python main.py --test-voice --output-device 4
.venv/bin/python main.py --monitor-input --input-device "BlackHole 2ch"
```

On this Mac, **Bose QC Ultra Headphones output is ID 4** (its microphone input is ID 3). Device IDs can change after reconnecting; rerun `--list-devices` before using a numeric ID, or pass `--output-device "Bose QC Ultra Headphones"` instead. `--test-voice` deliberately does not require BlackHole input or Ollama. It must speak Vietnamese through the headphones. During `--monitor-input`, play a clear English YouTube clip: RMS/peak should rise above silence, and you should **not** hear the English. Ctrl+C ends monitoring.

If Terminal asks for microphone permission, allow it for virtual BlackHole capture. If input stays at zero, check **System Settings > Privacy & Security > Microphone**, then restart Terminal and the app. `--monitor-input` reports levels only; it neither transcribes nor saves audio.

## P1: spoken translation

```bash
.venv/bin/python main.py --output-device 4
```

Startup verifies that the current macOS output is BlackHole 2ch, that the chosen output is physical, that the cached Whisper model exists, that Ollama has `translategemma:4b`, and that a Vietnamese voice exists. It warms both models before opening capture. Play an English YouTube talk. Expect `EN:`, `VI:`, per-stage timing, spoken start lag, and 10-second queue/drop health lines. Vietnamese should play through your headphones. **Press Ctrl+C to stop, then System Settings > Sound > Output > reselect your headphones.** Do this restoration even after errors or a crash.

Optional: `--text-only` checks ASR/translation without TTS; `--voice NAME` selects an installed Vietnamese voice; `--sample-rate 44100` selects the configured BlackHole rate; `--chunk-seconds 3` changes fixed segment length; `--max-lag 12` skips old work after 12 seconds. Defaults are 48 kHz capture, 4-second chunks and 12-second stale limit. Shorter chunks reduce wait but can split words and hurt translation.

The capture callback only copies buffers to a bounded queue. A segment worker downmixes/resamples; one inference worker preserves order through ASR and local translation; one speech worker synthesizes and plays to the selected output. When behind, the oldest queued items are dropped with visible counters. Capture continues while Vietnamese plays. No speaker identification or meeting memory is included.

## Manual acceptance on the M1 Pro

1. Confirm `--test-voice` is audible in the selected headphones, then stop it. Confirm the selected output is neither BlackHole nor a Multi-Output/aggregate device.
2. Set macOS output to BlackHole. Play a YouTube English talk and run `--monitor-input`. RMS/peak must rise while English remains inaudible in the headphones.
3. Run the translator. Confirm English text, Vietnamese text, then audible intelligible Vietnamese speech in source order. Record several displayed start-lag values; do not infer latency from chunk length alone.
4. Pause the source. Confirm no repeated Vietnamese speech or feedback. Check BlackHole input level stays near zero while TTS alone plays.
5. Try a Facebook video and a Meet call where remote speakers take turns. Confirm each app uses the system output route. Keep the real meeting microphone selected and verify TTS is not sent into the call.
6. Run for 15 minutes. Watch `[HEALTH]` queue sizes/drop counts and Activity Monitor memory pressure and swap. A busy 16 GB Mac may need closing other large apps; report observed values.
7. Stop with Ctrl+C and restore your headphones as macOS output. Test an ordinary video to confirm normal audio returned.

## Recovery and limits

- **No voice:** install a Vietnamese voice, then rerun `--list-voices`.
- **No BlackHole / silent level:** restart after driver install; select BlackHole as system output; allow Terminal/Python microphone permission; ensure the source app is not pinned to another output.
- **No Ollama/model:** `brew services start ollama`, `ollama list`, then `ollama pull translategemma:4b` while online.
- **Whisper missing:** repeat the `snapshot_download` setup command while online. Runtime deliberately refuses to download a model.
- **Headphones disconnect / TTS error:** stop, restore macOS output, reconnect, run `--list-devices`, and restart with the new ID.
- **High lag / drop counts:** observe measured lag first. Fixed 4-second chunks, ASR and translation time, and speech playback all add delay. The bounded queues intentionally skip old work rather than accumulating minutes of speech. P2 will improve segmentation and latency.

Protected media, app-specific output overrides, overlapping speakers, noisy music and Bluetooth reconnects can fail or reduce quality. This version does not restore system output automatically. Obtain meeting consent where required.
