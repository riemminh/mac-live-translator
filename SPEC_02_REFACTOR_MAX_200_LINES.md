# SPEC 02 — Folder-Based Refactor, Maximum 200 Lines per Python File

**Repository:** `riemminh/mac-live-translator`  
**Reviewed baseline:** `85892e59025ca18cd916cccffe4b41413529298a`  
**Depends on:** `SPEC_01_AUDIT_CLEANUP.md` for outdated docs, lockfile and privacy corrections  
**Outcome:** a readable, modular application with one main PySide6 app and stable launch commands, **no behavioral regression**.

## 1. Hard rules

1. Every **handwritten `.py` source file**, including entrypoints, `__init__.py` and helper scripts, is **≤200 physical lines** using `wc -l` (blank lines, comments and imports count). Generated files (`uv.lock`, downloaded models, docs, cache) are outside this source-code limit.
2. Split by **responsibility** (audio, ASR, translation, meeting, knowledge, Copilot, UI, CLI), not arbitrary 199-line chunks. Avoid one-line wrappers and dozens of trivial utilities unless they preserve a public command or clarify a real boundary.
3. **Simple → Correct → Maintainable → Optimize when needed**. Keep public behavior, current model choices, timestamp semantics, queues, event names, audio guards, metrics, and UI controls unless a separate focused bug fix is documented.
4. No unit tests unless explicitly requested; **manual regression checks plus syntax/import checks** are mandatory. Do not claim hardware verification without a target-Mac run.
5. Do not automatically commit/push or overwrite uncommitted changes. Do not introduce unrelated dependencies, web backend, vector DB, more local AI models, SwiftUI, or automatic Copilot calls.
6. Avoid `from ... import *`, circular imports, moving logic into `__init__.py`, or introducing a catch-all `utils.py`/`manager.py` with the same old complexity.
7. Translation must remain **100% local**. Claude stays opt-in on demand, with clearly bounded sharing of selected transcript/doc excerpts.

## 2. Target folder tree (proposed; adjust module boundaries if needed)

```text
mac-live-translator/
├── ui.py                            # <=20 lines: existing GUI command wrapper
├── main.py                          # <=25 lines: existing CLI command wrapper
├── live_pipeline.py                 # <=20 lines: optional compatibility wrapper; remove only after callers checked
├── pyproject.toml
├── uv.lock
├── README.md
├── AGENTS.md
├── SPEC.md                         # updated current product/architecture, docs not subject to Python LOC rule
├── .gitignore
├── docs/
│   ├── architecture.md
│   ├── benchmarks/                 # historical measurements and caveats
│   └── legacy/                     # optional archived old CLI/TTS guides
└── mac_live_translator/
    ├── __init__.py
    ├── config.py                   # <=130: Config, paths, model constants, validation
    ├── events.py                   # <=90: event names/type hints (no heavy event framework)
    ├── audio/
    │   ├── __init__.py
    │   ├── devices.py              # <=170: enumerate, resolve, identity, check output
    │   ├── routing.py              # <=135: BlackHole/Multi-Output route guards
    │   ├── capture.py              # <=170: callback -> bounded audio queue
    │   ├── monitor.py              # <=110: diagnostic RMS/peak capture
    │   └── tts.py                  # <=160: optional legacy macOS voice and physical output
    ├── asr/
    │   ├── __init__.py
    │   ├── whisper.py              # <=100: model preparation, transcribe wrapper
    │   ├── segmentation.py         # <=185: streaming audio window/silence segmentation
    │   └── stability.py            # <=140: tokens, stable prefix, phrase cut policy
    ├── translation/
    │   ├── __init__.py
    │   ├── ollama.py               # <=175: local translate, stream, availability
    │   ├── models.py               # <=100: Segment/Fragment dataclasses
    │   ├── policy.py               # <=145: glossary, filler, risky boundaries
    │   ├── scheduler.py            # <=175: high/low priority bounded jobs, pruning
    │   ├── worker.py               # <=190: translate/stream and revision checks
    │   └── reconcile.py            # <=140: selective final reconciliation
    ├── pipeline/
    │   ├── __init__.py
    │   ├── live.py                 # <=185: lifecycle and composition of existing workers
    │   └── metrics.py              # <=165: traces, coverage, latency counters
    ├── meeting/
    │   ├── __init__.py
    │   ├── models.py               # <=75: immutable TranscriptEntry
    │   ├── context.py              # <=175: bounded MeetingContextStore
    │   └── retrieval.py            # <=165: recent/older lookup and prompt formatting
    ├── knowledge/
    │   ├── __init__.py
    │   ├── models.py               # <=75: DocumentChunk
    │   ├── loader.py               # <=145: selected file/folder scan, safe read
    │   ├── chunker.py              # <=145: heading and paragraph chunks
    │   └── store.py                # <=185: memory SQLite FTS5 + reindex/search
    ├── copilot/
    │   ├── __init__.py
    │   ├── client.py               # <=175: official Anthropic SDK, streaming/cancel/usage
    │   ├── prompts.py              # <=110: system instruction + context template
    │   ├── parser.py               # <=125: English/VI sections and source ID validation
    │   └── assistant.py            # <=185: retrieve -> prompt -> Claude -> result
    ├── gui/
    │   ├── __init__.py
    │   ├── app.py                  # <=60: QApplication setup
    │   ├── window.py               # <=145: QMainWindow composition, start/stop wiring
    │   ├── translation_tab.py      # <=190: translation widgets and controls
    │   ├── translation_events.py   # <=195: live ASR/VI event handling and revision view
    │   ├── translation_metrics.py  # <=175: p50/p95, trace formatting, health
    │   ├── copilot_tab.py          # <=165: QTab/sections composition
    │   ├── copilot_panels.py       # <=195: privacy, knowledge, question/result widgets
    │   ├── copilot_actions.py      # <=195: request flow, consent, cancellation, results
    │   └── workers.py              # <=120: QThread wrappers, safe signals/lifecycle
    └── cli/
        ├── __init__.py
        ├── commands.py             # <=185: argparse/device diagnostics
        ├── legacy_session.py       # <=190: optional CLI fixed-chunk mode coordinator
        └── legacy_workers.py       # <=185: optional CLI segment/infer/TTS workers
```

This tree is a **responsibility map, not an instruction to create empty files**. Combine modules where they remain comfortably ≤200 lines; split a module further only when actual code requires it. The right number of files is determined by clear ownership and the hard line cap, not a target file count.

## 3. Source-to-target mapping

| Existing file | Move code into | Notes |
|---|---|---|
| `main.py` | `config.py`, `audio/devices.py`, `audio/routing.py`, `audio/tts.py`, `audio/monitor.py`, `asr/whisper.py`, `translation/ollama.py`, `cli/*` | It currently serves as a **shared library** for GUI AND CLI. Break `import main as core` before shrinking entrypoint. Preserve device routing and optional CLI paths. |
| `live_pipeline.py` | `asr/segmentation.py`, `asr/stability.py`, `translation/models.py`, `translation/policy.py`, `translation/scheduler.py`, `translation/worker.py`, `translation/reconcile.py`, `pipeline/live.py`, `pipeline/metrics.py` | Extract existing logic, preserve ordering/backpressure and event names. No algorithm rewrite during move. |
| `ui.py` | `gui/app.py`, `gui/window.py`, `gui/translation_tab.py`, `gui/translation_events.py`, `gui/translation_metrics.py`, `gui/copilot_tab.py`, `gui/copilot_panels.py`, `gui/copilot_actions.py`, `gui/workers.py` | Preserve the two tabs, Start/Stop, focus/history, QTimer event drain, copy/cancel and preview/final behavior. |
| `meeting_context.py` | `meeting/models.py`, `meeting/context.py`, `meeting/retrieval.py` | Retain bounded RAM, chronological IDs and immutable snapshots; avoid unnecessary split if <=200. |
| `knowledge_store.py` | `knowledge/models.py`, `knowledge/loader.py`, `knowledge/chunker.py`, `knowledge/store.py` | Index scope and duplicate/reindex behavior are separate from directory moves; follow Spec 01. |
| `claude_client.py` | `copilot/client.py` (+ `copilot/models.py` **only if needed**) | Prefer one SDK codepath; no silent fallback. |
| `meeting_assistant.py` | `copilot/prompts.py`, `copilot/parser.py`, `copilot/assistant.py` | Keep retrieval, response formatting and source ID checks distinct. |

## 4. Import and dependency rules

- Prefer **absolute package imports** (e.g. `from mac_live_translator.translation.ollama import translate_stream`) or simple intra-package relative imports consistently. Avoid dynamic imports and path hacks.
- `gui` may import `pipeline`, `meeting`, `knowledge`, `copilot`; **none** of those may import `gui`.
- `pipeline` coordinates audio, ASR and translation. `translation` should **not import `main.py`** or PySide6. `audio` must not import Copilot.
- `copilot` imports meeting/knowledge snapshots and its Claude client, **never** the live Ollama translation worker. Claude failures must not propagate into the audio pipeline.
- `config.py` and `events.py` are dependency-light. Avoid global singleton `Window` or mutable cross-module application state.
- Keep current `emit(kind: str, data: dict)` event contract during refactor, not a speculative event bus/framework.
- External entrypoints remain working:
  - `uv run --locked python ui.py`
  - `uv run --locked python main.py --list-devices`
  - `uv run --locked python main.py --monitor-input --input-device "BlackHole 2ch"`
  - `uv run --locked python main.py --speak --output-device "..."` (optional existing CLI; preserve until explicitly deprecated)

Example wrappers:

```python
# ui.py
from mac_live_translator.gui.app import main

if __name__ == "__main__":
    main()
```

```python
# main.py
from mac_live_translator.cli.commands import main

if __name__ == "__main__":
    main()
```

Avoid keeping the old implementation duplicated under the wrappers.

## 5. Preserve these exact behavioral invariants

### Audio & local inference

- BlackHole 2ch, Multi-Output routing for GUI text mode, audio loop/feedback safeguards, selected physical headphones identity, Stop/recovery behavior.
- 20ms audio capture blocks, bounded queues, no inference or disk I/O in PortAudio callback.
- Whisper Small.en, overlapping partial ASR, stable-prefix logic, unchanged speech thresholds initially.
- TranslateGemma 4B local Ollama, streaming VI fragments, revisions, obsolete cancellation, high-priority new fragments and lower-priority reconciliation, constrained queue size and drop/error notifications.
- Local translation must work with no Claude key or Internet; no newly required LLMs.

### Events, metrics & UI

Preserve event `kind` and payload semantics for at least:

`status`, `stopped`, `english_partial`, `english_final`, `vietnamese_partial`, `vietnamese_final`, `translation_revision`, `vietnamese_cancelled`, `trace`, `coverage`, `coverage_final`, `translation_delayed`, `translation_skipped`, `ollama_stats`, `health`.

Preserve segment IDs, revisions, filler flags, source timestamps, queue wait, p50/p95, dropped/coverage indicators and once-only history lines.

- Both PySide6 tabs remain in one application; changing tab never restarts ASR/Ollama.
- Latest English partial and VI streaming are readable; history scroll position is stable; no old revision overwrites new text.
- Copilot still provides Help Me Reply, Explain Context, Suggest Question, user question override, selected MD/TXT, English + Vietnamese + sources, cancellation and Copy.
- Keep QThread signals on the UI thread; no blocking HTTP, directory scan or heavy processing on the Qt UI thread.

### Privacy and correctness

- Local meeting context and knowledge indexes remain memory-only by default.
- Cloud opt-in must be explicit; providing an API key must not automatically enable sharing.
- Claude receives only bounded relevant source excerpts after user action; never send whole folders/transcripts by default.
- Never assume speaker identity, project status, deadlines or commitments. Keep transcript/document IDs traceable to actual retrieved content.

## 6. Migration phases (small, reversible slices)

**Phase 0 — Baseline and cleanup dependency:**

- Follow Spec 01 first: resolve stale `uv.lock` (Anthropic missing), privacy opt-in and tracked caches.
- Inspect actual local `git status` / HEAD and preserve uncommitted changes.
- List all callers/imports and CLI commands; record current translation/Copilot manual behaviors and benchmark metrics.

**Phase 1 — Core / audio / translation adapters:**

- Create package directories and `__init__.py` files.
- Extract `Config`/constants, audio device identity/route checks, Whisper wrapper and Ollama wrapper from `main.py`; keep thin compatibility imports as needed during migration.
- Move CLI-specific TTS and diagnostics into `audio/` + `cli/`. Preserve `main.py --list-devices`, `--test-voice`, and other documented flags.
- After each move, run import/syntax checks and verify circular imports are gone.

**Phase 2 — Live pipeline decomposition:**

- Move `Fragment`, `Segment`, token/stable-prefix/filler/boundary policy into typed small modules.
- Extract audio capture and ASR segmentation into independent workers/functions.
- Extract prioritized scheduler and translation/reconciliation into their modules.
- Make `pipeline/live.py` only compose lifecycle/worker setup and route emitted events. Avoid introducing a complex class hierarchy just to satisfy line count.
- Ensure `live_pipeline.py` compatibility wrapper delegates to `pipeline.live.run` until all imports are migrated.

**Phase 3 — Meeting / knowledge / Claude services:**

- Move context and retrieval code, knowledge file loading/chunking/indexing and Copilot prompts/parser/service to their packages.
- Keep same external behavior, tighten lifecycle and consent defects from Spec 01, and make context snapshot boundaries explicit.
- Preserve source references and no persistence by default.

**Phase 4 — PySide6 modularization:**

- Extract tab widget builders into self-contained `TranslationTab` and `CopilotTab` view classes or cohesive functions.
- Create slim `Window` composition responsible only for wiring/central lifecycle.
- Route transcript/subtitle events and metrics through separate handler modules (keep order and revision rules).
- Put QThreads in `gui/workers.py`; maintain strong references and proper cancellation/cleanup for indexing and Claude requests.
- Do not mix model API calls inside widget-building functions.

**Phase 5 — Simplify entrypoints and update docs:**

- Turn root `ui.py` and `main.py` into tiny stable wrappers; keep `live_pipeline.py` wrapper only if compatibility is needed.
- Update README startup commands, module map, AGENTS, SPEC and any error text referencing old paths.
- Ensure all handwritten Python source files are ≤200 lines.

**Phase 6 — Manual acceptance / benchmark:**

- Validate syntax and imports, the frozen `uv.lock`, `git diff --check`, current CLI commands, 5-minute realtime subtitles, Copilot RAG request, consent behavior, cancel/restart, device detach and offline fallback.
- Compare current EN/VI p50/p95, skip/coverage counters, semantic quality and Copilot TTFT against baseline. No claim of improvement without measured evidence.

## 7. Source file length gate

Run this from the repo root **after** all new files have been created (works before `git add`):

```bash
python - <<'PY'
from pathlib import Path
SKIP = {'.git', '.venv', '__pycache__', '.pytest_cache', '.mypy_cache'}
violations = []
for file in Path('.').rglob('*.py'):
    if any(part in SKIP for part in file.parts):
        continue
    count = len(file.read_text(encoding='utf-8').splitlines())
    if count > 200:
        violations.append((count, str(file)))
if violations:
    for count, path in sorted(violations, reverse=True):
        print(f'OVER 200: {count} lines: {path}')
    raise SystemExit(1)
print('PASS: all handwritten Python files <=200 lines')
PY
```

The check should be **a hard acceptance gate**, not a reason to compress code into unreadable single-line statements. Aim for ~100–180 lines in normal modules to leave room for maintenance.

## 8. Validation checklist

```bash
uv sync --locked
uv run --locked python -m compileall -q mac_live_translator ui.py main.py
uv run --locked python -c 'import mac_live_translator.gui.app; import mac_live_translator.pipeline.live; import mac_live_translator.copilot.assistant'
git diff --check
uv run --locked python main.py --list-devices
uv run --locked python ui.py
```

**Manually on the M1 Pro:**

1. Start/Stop translation with actual BlackHole + headphones; no route or feedback regression.
2. Play the same five-minute YouTube segment at 1x without interruption; compare first EN, first visible VI, final VI, p50/p95, queue depth, dropped and translation meaning.
3. Verify stable-prefix corrections, stale fragment cancellation, filler handling and prior-thought display.
4. Switch GUI tabs while capture and translation continue.
5. With explicit cloud opt-in, ask about the GitLab beta→GA transcript and a selected MD file; English reply streams cleanly, Vietnamese/evidence are correctly separated.
6. Retry multiple indexing operations, cancel API request, start a new meeting, and close window during pending work. No stale cross-session result or Qt thread crash.
7. Remove the key / disconnect Internet; Live Translation remains functional.
8. Run `git diff` and inspect that changes are moves/extractions, not lost functionality.

## 9. Done criteria and required Gemini report

- **No handwritten `.py` file >200 physical lines.**
- All primary logic resides under coherent folders; wrappers at root retain current commands.
- No remaining `import main as core` coupling from translation/pipeline to a CLI entrypoint; no circular import or unnecessary global state.
- No duplicate old implementations kept after successful migration.
- Live EN/VI translation and Copilot continue to function, with current route safety, privacy and manual verification evidence.
- Documentation reflects actual modules and scope; `uv sync --locked` works from the repo.

Report **phase-by-phase**: files moved, previous/new function ownership, imports changed, checks performed, functions intentionally kept as legacy, remaining risks, and any unverified Mac-specific behavior. Do not silently remove TTS CLI, core thresholds, log formats or event payloads.
