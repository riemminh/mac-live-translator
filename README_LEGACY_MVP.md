# Mac Live Voice Translator — M1 Pro / 16GB MVP

An **experimental 100% local** English system-audio → Vietnamese speech proof of concept for macOS. Works for whatever produces sound through the selected macOS output (YouTube, Facebook, Meet, etc.). **No subtitles or meeting memory are required.**

**Not yet a one-click native app.** This first version uses macOS's own Vietnamese voice (`say`) instead of a second large TTS model, a 4-bit Ollama translation model, and MLX Whisper on Apple Silicon. After initial model downloads, processing uses local services and no cloud inference API. Do not assume an offline machine can download models or voice assets.

## Audio routing (critical)

```
Browser / Meet / apps → macOS System Output: BlackHole 2ch
                                     ↓
                        Python BlackHole input
                                     ↓
                Whisper → Ollama → macOS say TTS
                                     ↓
                  Python output: physical headphones
```

Selecting **BlackHole 2ch alone** as your system output means **the original English audio does NOT go to your headphones**, unlike the usual Multi-Output Device setup. The translated voice is played to the physical headphone device via a separate explicit audio output. This avoids an infinite feedback loop. While app is running, *all* system sounds routed to BlackHole (including alerts/music) will be inaudible unless translated. You can still use your microphone normally in a meeting; choose your physical microphone in Meet. If app stops, restore your normal headphone output in macOS Sound Settings.

## Requirements

- Apple Silicon Mac; Python 3.11 or 3.12 (arm64); ~16GB RAM recommended for this config
- macOS Ventura/Sonoma or later (BlackHole audio driver)
- [BlackHole 2ch](https://github.com/ExistentialAudio/BlackHole), `brew install blackhole-2ch` (may need restarting audio apps)
- [Ollama](https://ollama.com/) installed and serving on local port 11434
- macOS Vietnamese system voice installed. Find in macOS **System Settings → Accessibility → Spoken Content / Read & Speak → System Voice** and download a Vietnamese voice. The menu labels vary by macOS version.
- Physical headphones plugged in and available as a distinct audio output device. Headphones are preferable to built-in speakers.

## Installation

```bash
brew install ffmpeg blackhole-2ch
ollama pull translategemma:4b
# Launch Ollama app (or `ollama serve` if it isn't already running)

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

First MLX Whisper transcription downloads `mlx-community/whisper-small.en-mlx` from Hugging Face (~481 MB). `translategemma:4b` downloads ~3.3GB. Voice assets may need separate one-time download.

## Check audio devices and TTS

```bash
python main.py --list-devices
python main.py --list-voices
```

Identify the numeric device ID of your physical headphones, for example `7`. **Do not choose BlackHole or a Multi-Output Device as output.** Confirm a Vietnamese voice exists.

Test Vietnamese speech directly into the selected headphones:

```bash
python main.py --output-device 7 --test-voice
```

If this fails, check the macOS audio device/voice installation before proceeding.

## Run (step by step)

1. Open **System Settings → Sound → Output** and select **BlackHole 2ch** (NOT Multi-Output Device). Make a note of your normal headphone output so you can restore it later.
2. If prompted for microphone permission for Terminal/Python, allow it to capture the virtual BlackHole device (this isn't recording your physical microphone).
3. Start:

```bash
# Replace 7 with the real physical headphone output ID.
python main.py --output-device 7
```

4. Play a clear English video. Expected Terminal logs:

```
EN: Welcome to today's presentation.
VI: Chào mừng bạn đến với bài thuyết trình hôm nay.
```

The Vietnamese sentence is synthesized by macOS and played to your selected headphones.
5. Stop with **Ctrl+C**. Return to **Sound → Output** and reselect your physical headphones.

### Debug / test just transcription and translation

```bash
python main.py --output-device 7 --text-only
```

With `--text-only`, no Vietnamese voice is required. To reduce recognition latency, try `--chunk-seconds 3`, but shorter chunks can hurt transcription/translation accuracy.

### Optional args

- `--input-device "BlackHole 2ch"` (or number, default is BlackHole 2ch)
- `--output-device 7` (physical output; required)
- `--sample-rate 48000` (or 44100 if BlackHole is configured that way)
- `--voice Linh` if a Vietnamese voice with this exact installed name appears in `--list-voices`
- `--whisper-model mlx-community/whisper-base.en-mlx` for a lighter model
- `--min-rms 0.004` to change silence threshold

## Known limitations

- **Prototype only**, not tested on a real M1 Pro by the author; Python syntax checked.
- **Not truly simultaneous**: chunks of audio (~4 seconds) are transcribed, then translated, then spoken. Delay may exceed chunk size, especially when the speaker continues talking or the machine is busy.
- **No speech separation or speaker identification**. Overlapping voices from Meet can reduce accuracy.
- **Audio is not saved**; each chunk is transient and only the text appears in terminal. No meeting memory or history database.
- **No background music pass-through**; original audio is muted by BlackHole routing. This is intended for speech videos and calls, not music.
- If TTS cannot keep up, oldest queued Vietnamese translations are skipped so latency doesn't grow forever.
- Occasional Whisper misrecognition and mistranslation are possible, especially with short phrases or mixed languages.
- Headphone reconnects, switching sample rates, Bluetooth devices, and device availability changes can require restarting the script.
- The Mac and/or Chrome can open a different system/app audio output; make sure the application uses your macOS system output (BlackHole).
- Audio may be captured/transcribed under workplace or meeting policies; obtain consent where required.

## Next version (not implemented)

- Native Swift **Core Audio Process Tap** capture+mute replaces BlackHole and the manual output switch. This is possible on supported macOS versions but needs per-OS testing.
- Higher-quality local Vietnamese TTS (VieNeu-TTS v3 Turbo) and streaming segments.
- A menu bar app with on/off, device selection, crash-safe audio restoration, global hotkey.

## Privacy

No files persist audio, transcripts, or translation. Speech is converted to temporary local audio (`say` output) and erased automatically. Network is used initially to download Hugging Face/ Ollama models; subsequent requests go only to `127.0.0.1` for Ollama and local inference with MLX. Model caches persist on disk. Check your organization's policies before capturing meetings.
