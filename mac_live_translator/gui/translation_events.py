"""Event dispatchers and metric updates for live speech transcription and subtitles."""

from __future__ import annotations

import statistics
import time
from typing import TYPE_CHECKING
from PySide6.QtWidgets import QTextEdit

if TYPE_CHECKING:
    from mac_live_translator.gui.window import Window


def show_history(view: QTextEdit, lines: list[str]) -> None:
    """Update a transcript view preserving scroll position unless at the bottom."""
    scrollbar = view.verticalScrollBar()
    old_position = scrollbar.value()
    old_maximum = scrollbar.maximum()
    view.setPlainText("\n".join(lines))
    if old_position:
        scrollbar.setValue(old_position + scrollbar.maximum() - old_maximum)
    else:
        scrollbar.setValue(0)


def handle_translation_event(win: Window, kind: str, data: dict) -> None:
    """Route and process incoming background pipeline events into the UI."""
    if kind == "english_partial" and data["id"] not in win.final_en_ids:
        if win.current_id is not None and data["id"] < win.current_id:
            return
        win.current_id = data["id"]
        win.first_english.setdefault(data["id"], data["latency"])
        stable = data["stable"]
        is_fill = data.get("is_filler", False)
        if not is_fill:
            win.english_live.setText(f"Hearing: {data['text']}  |  Stable: {stable}")
        rendered_vi = win.first_vietnamese_rendered.get(data["id"])
        vi_str = f"{rendered_vi:.2f}s" if rendered_vi is not None else "—"
        win.metrics.setText(f"Audio → first EN: {win.first_english[data['id']]:.2f}s  ·  first VI: {vi_str}  ·  final VI: —")

    elif kind == "english_final" and data["id"] not in win.final_en_ids:
        win.first_english.setdefault(data["id"], data["latency"])
        win.final_en_ids.add(data["id"])
        win.current_id = data["id"]
        is_fill = data.get("is_filler", False)
        tag = f"[{data['id']}]" + (" (filler)" if is_fill else "")
        win.final_en.insert(0, f"{tag} {data['text']}")
        del win.final_en[150:]
        show_history(win.english, win.final_en)
        if not is_fill:
            win.english_live.setText(f"Completed: {data['text']}")
        rendered_vi = win.first_vietnamese_rendered.get(data["id"])
        vi_str = f"{rendered_vi:.2f}s" if rendered_vi is not None else "—"
        win.metrics.setText(f"Audio → first EN: {win.first_english[data['id']]:.2f}s  ·  first VI: {vi_str}  ·  final VI: —")
        win.status.setText(f"Listening · final English {data['latency']:.1f}s")
        win.context_store.add_segment(segment_id=data["id"], text=data["text"], is_filler=is_fill)
        win.copilot_actions.update_context_status()

    elif kind == "translation_revision":
        print(f"REVISION id={data['id']} version={data['revision']}", flush=True)
        if data["revision"] > win.vi_revisions.get(data["id"], -1):
            win.vi_revisions[data["id"]] = data["revision"]
            if win.preview_id == data["id"]:
                preview = data.get("preview", "")
                win.vietnamese_live.setText(f"[{data['id']}] Bản nháp · {preview}" if preview else "Đang dịch…")

    elif kind == "vietnamese_partial" and data["id"] not in win.final_vi_ids:
        if data.get("revision", 0) < win.vi_revisions.get(data["id"], -1):
            return
        win.vi_revisions[data["id"]] = data.get("revision", 0)
        if win.preview_id is not None and data["id"] < win.preview_id:
            return
        win.preview_id = data["id"]
        now = time.monotonic()
        is_filler = data.get("is_filler", False)
        if not is_filler:
            win.vietnamese_live.setText(f"[{data['id']}] Bản nháp · {data['text']}")
            trace = win.traces.setdefault(data["id"], {})
            origin = trace.get("source_start")
            if data["id"] not in win.first_vietnamese_rendered:
                rendered_lat = (now - origin) if origin is not None else data["latency"]
                win.first_vietnamese_rendered[data["id"]] = rendered_lat
                trace.setdefault("first_token_rendered", now)
        win.first_vietnamese_received.setdefault(data["id"], data["latency"])
        rendered_lat = win.first_vietnamese_rendered.get(data["id"])
        first_en = win.first_english.get(data["id"])
        en_str = f"{first_en:.2f}s" if first_en is not None else "—"
        vi_str = f"{rendered_lat:.2f}s" if rendered_lat is not None else "—"
        win.metrics.setText(f"Audio → first EN: {en_str}  ·  first VI: {vi_str}  ·  final VI: —")

    elif kind == "vietnamese_cancelled":
        if win.preview_id == data["id"]:
            win.vietnamese_live.setText("Đang lắng nghe cuộc họp…")
            win.preview_id = None

    elif kind == "vietnamese_final" and data["id"] not in win.final_vi_ids:
        win.final_vi_ids.add(data["id"])
        now = time.monotonic()
        is_fill = data.get("is_filler", False)
        tag = f"[{data['id']}]" + (" (filler)" if is_fill else "")
        win.final_vi.insert(0, f"{tag} {data['text']}")
        del win.final_vi[150:]
        show_history(win.vietnamese, win.final_vi)
        if not is_fill:
            win.recent_thought_groups.append(f"[{data['id']}] {data['text']}")
            win.context_label.setText("Ngữ cảnh gần nhất: " + "  •  ".join(win.recent_thought_groups))
            if win.preview_id == data["id"]:
                win.vietnamese_live.setText(f"[{data['id']}] Hoàn tất · {data['text']}")
                win.preview_id = None
        first_rendered = win.first_vietnamese_rendered.get(data["id"])
        if first_rendered is None:
            first_rendered = data["latency"]
            win.first_vietnamese_rendered[data["id"]] = first_rendered
            win.traces.setdefault(data["id"], {}).setdefault("first_token_rendered", now)
        first_received = win.first_vietnamese_received.get(data["id"], data.get("first_token_received_latency", first_rendered))
        first_en = win.first_english.get(data["id"])
        if first_en is not None:
            win.metrics.setText(f"Audio → first EN: {first_en:.2f}s  ·  first VI: {first_rendered:.2f}s  ·  final VI: {data['latency']:.2f}s")
            win.results.append((first_en, first_rendered, data["latency"], first_received or first_rendered))
            print(f"METRIC id={data['id']} audio_to_first_en={first_en:.3f}s audio_to_first_vi_rendered={first_rendered:.3f}s audio_to_first_vi_received={first_received if first_received is not None else first_rendered:.3f}s audio_to_final_vi={data['latency']:.3f}s", flush=True)
            trace = win.traces.get(data["id"], {})
            origin = trace.get("source_start")
            if origin is not None:
                def elapsed(stage: str) -> str:
                    val = trace.get(stage)
                    return f"{val - origin:.3f}" if val is not None else "—"
                q, dq = trace.get("queued"), trace.get("dequeued")
                wait = f"{dq - q:.3f}" if q is not None and dq is not None else "—"
                req_s, req_d = trace.get("request_start"), trace.get("translation_done")
                req_dur = f"{req_d - req_s:.3f}" if req_s is not None and req_d is not None else "—"
                print(f"TRACE id={data['id']} first_en_ready={elapsed('first_en_ready')} stable={elapsed('stable')} eligible={elapsed('eligible')} final_en={elapsed('final_en')} queue_wait={wait} request_start={elapsed('request_start')} first_token_received={elapsed('first_token_received')} first_token_rendered={elapsed('first_token_rendered')} request_duration={req_dur}", flush=True)
        win.status.setText(f"Listening · first token {first_rendered:.1f}s · final {data['latency']:.1f}s")

    elif kind == "trace":
        tr = win.traces.setdefault(data["id"], {})
        tr.setdefault("source_start", data["source_start"])
        tr.setdefault(data["stage"], data["at"])
        if any(k in data for k in ("fragment_id", "stable_wait", "request_duration", "duration")):
            extra = " ".join(f"{name}={value:.3f}s" if name in {"stable_wait", "queue_wait", "request_duration", "duration"} else f"{name}={value}" for name, value in data.items() if name in {"fragment_id", "revision", "stable_wait", "queue_wait", "queue_size", "request_duration", "duration"})
            print(f"TRACE id={data['id']} stage={data['stage']} audio_elapsed={data['at'] - data['source_start']:.3f}s {extra}", flush=True)

    elif kind == "coverage":
        print(f"COVERAGE id={data['id']} fragment={data['fragment_id']} english_words={data['words']} backlog={data['queue_size']}", flush=True)

    elif kind == "coverage_final":
        for name in ("english_words", "covered_words", "fragments", "revisions"):
            win.coverage[name] += data[name]
        print(f"COVERAGE_FINAL id={data['id']} english_words={data['english_words']} covered_words={data['covered_words']} fragments={data['fragments']} revisions={data['revisions']}", flush=True)

    elif kind == "translation_delayed":
        win.status.setText(f"Listening · translation queue wait {data['wait']:.1f}s")

    elif kind == "ollama_stats":
        frag_info = f" fragment={data['fragment_id']}" if "fragment_id" in data else ""
        print(f"OLLAMA id={data['id']}{frag_info} load={data['load_ms']:.1f}ms prompt={data['prompt_ms']:.1f}ms eval={data['eval_ms']:.1f}ms", flush=True)

    elif kind == "translation_skipped":
        win.coverage["skipped"] += 1
        print(f"SKIPPED id={data['id']} reason={data['reason']}", flush=True)
        if data["reason"] in {"audio overflow", "queue full; stopping to avoid lost words"}:
            win.status.setText(f"Listening · skipped speech: {data['reason']}")

    elif kind == "health" and any(data["dropped"].values()):
        win.status.setText(f"Listening · dropped {data['dropped']} · translation backlog {data['translation_backlog']}")

    elif kind == "status":
        win.status.setText(data["text"])

    elif kind == "stopped":
        win.vietnamese_live.setText("Stopped")
        win.english_live.setText("")
        win.preview_id = None
        if win.results:
            columns = list(zip(*win.results))
            def p95(values: tuple[float, ...]) -> float:
                ordered = sorted(values)
                return ordered[max(0, int(0.95 * len(ordered) + 0.999) - 1)]
            names = ("first_en", "first_vi_rendered", "final_vi", "first_vi_received")
            print(f"BENCHMARK n={len(win.results)} " + " ".join(f"{name}_p50={statistics.median(values):.3f}s {name}_p95={p95(values):.3f}s" for name, values in zip(names, columns)), flush=True)
        print("COVERAGE_SUMMARY " + " ".join(f"{key}={value}" for key, value in win.coverage.items()), flush=True)
        win.start_button.setEnabled(True)
        win.stop_button.setEnabled(False)
        if not win.status.text().startswith("Error:"):
            win.status.setText("Stopped")

