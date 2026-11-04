"""Claude Haiku 5.5 streaming client supporting both the Anthropic SDK and resilient HTTP streaming."""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from typing import Callable

import requests

DEFAULT_MODEL = "claude-haiku-5-5"
FALLBACK_MODEL = "claude-3-5-haiku-20241022"
API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


@dataclass
class ClaudeUsage:
    """Usage and latency statistics for an executed Claude request."""
    input_tokens: int = 0
    output_tokens: int = 0
    time_to_first_token: float = 0.0
    total_duration: float = 0.0
    model: str = DEFAULT_MODEL


class ClaudeClientError(Exception):
    """Base exception for Claude API failures."""
    pass


class ClaudeClient:
    """Client for Anthropic Claude models with streaming, thinking delta separation, and cancellation."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        max_tokens: int = 1024,
    ) -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "").strip()
        self.model = model
        self.max_tokens = max_tokens

    def is_configured(self) -> bool:
        """Return True if an API key is available."""
        return bool(self.api_key and len(self.api_key) > 8)

    def stream_chat(
        self,
        system_prompt: str,
        user_message: str,
        on_text: Callable[[str], None],
        on_thinking: Callable[[str], None] | None = None,
        on_request_start: Callable[[], None] | None = None,
        stop_event: threading.Event | None = None,
    ) -> tuple[str, ClaudeUsage]:
        """Stream a chat request to Claude, delivering tokens as they arrive."""
        if not self.is_configured():
            raise ClaudeClientError("Anthropic API key is not configured. Please enter your key in the Copilot tab.")

        # Try official Anthropic SDK first if installed
        try:
            import anthropic  # type: ignore
            return self._stream_with_sdk(
                anthropic,
                system_prompt,
                user_message,
                on_text,
                on_thinking,
                on_request_start,
                stop_event,
            )
        except ImportError:
            # Resilient fallback to direct HTTP streaming via requests
            return self._stream_with_http(
                system_prompt,
                user_message,
                on_text,
                on_thinking,
                on_request_start,
                stop_event,
            )

    def _stream_with_sdk(
        self,
        anthropic_module: object,
        system_prompt: str,
        user_message: str,
        on_text: Callable[[str], None],
        on_thinking: Callable[[str], None] | None = None,
        on_request_start: Callable[[], None] | None = None,
        stop_event: threading.Event | None = None,
    ) -> tuple[str, ClaudeUsage]:
        """Stream using official Anthropic Python SDK."""
        client = getattr(anthropic_module, "Anthropic")(api_key=self.api_key)
        start_time = time.monotonic()
        if on_request_start:
            on_request_start()

        full_text: list[str] = []
        first_token_time: float | None = None
        usage = ClaudeUsage(model=self.model)

        # Attempt primary model; if alias unaccepted, try fallback
        for target_model in (self.model, FALLBACK_MODEL):
            try:
                with client.messages.stream(
                    model=target_model,
                    max_tokens=self.max_tokens,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                ) as stream:
                    for event in stream:
                        if stop_event and stop_event.is_set():
                            break
                        event_type = getattr(event, "type", "")
                        if event_type == "content_block_delta":
                            delta = getattr(event, "delta", None)
                            delta_type = getattr(delta, "type", "")
                            if delta_type == "text_delta":
                                token = getattr(delta, "text", "")
                                if token:
                                    if first_token_time is None:
                                        first_token_time = time.monotonic() - start_time
                                    full_text.append(token)
                                    on_text(token)
                            elif delta_type == "thinking_delta":
                                thinking_token = getattr(delta, "thinking", "")
                                if thinking_token and on_thinking:
                                    on_thinking(thinking_token)

                    final_msg = stream.get_final_message()
                    if final_msg and hasattr(final_msg, "usage"):
                        usage.input_tokens = getattr(final_msg.usage, "input_tokens", 0)
                        usage.output_tokens = getattr(final_msg.usage, "output_tokens", 0)

                usage.model = target_model
                break
            except Exception as exc:
                err_str = str(exc).casefold()
                if "model" in err_str and target_model != FALLBACK_MODEL:
                    continue  # Try fallback model
                raise ClaudeClientError(f"Anthropic SDK error: {exc}") from exc

        now = time.monotonic()
        usage.total_duration = now - start_time
        usage.time_to_first_token = first_token_time or usage.total_duration
        return "".join(full_text), usage

    def _stream_with_http(
        self,
        system_prompt: str,
        user_message: str,
        on_text: Callable[[str], None],
        on_thinking: Callable[[str], None] | None = None,
        on_request_start: Callable[[], None] | None = None,
        stop_event: threading.Event | None = None,
    ) -> tuple[str, ClaudeUsage]:
        """Stream directly using Anthropic Messages SSE protocol."""
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        }
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_message}],
            "stream": True,
        }

        start_time = time.monotonic()
        if on_request_start:
            on_request_start()

        full_text: list[str] = []
        first_token_time: float | None = None
        usage = ClaudeUsage(model=self.model)

        with requests.Session() as session:
            session.trust_env = False
            for target_model in (self.model, FALLBACK_MODEL):
                payload["model"] = target_model
                try:
                    with session.post(API_URL, headers=headers, json=payload, stream=True, timeout=(6, 45)) as resp:
                        if resp.status_code == 404 or (resp.status_code == 400 and "model" in resp.text.casefold()):
                            if target_model != FALLBACK_MODEL:
                                continue  # Try fallback model
                        if resp.status_code == 401:
                            raise ClaudeClientError("Invalid Anthropic API Key (401 Unauthorized).")
                        if resp.status_code == 429:
                            raise ClaudeClientError("Anthropic rate limit reached (429). Please retry shortly.")
                        if resp.status_code >= 500:
                            raise ClaudeClientError(f"Anthropic server error ({resp.status_code}). Please retry.")
                        resp.raise_for_status()

                        for line in resp.iter_lines():
                            if stop_event and stop_event.is_set():
                                break
                            if not line:
                                continue
                            line_str = line.decode("utf-8", errors="replace")
                            if line_str.startswith("data: "):
                                data_json = line_str[6:].strip()
                                if data_json == "[DONE]":
                                    break
                                try:
                                    data = json.loads(data_json)
                                except json.JSONDecodeError:
                                    continue

                                event_type = data.get("type", "")
                                if event_type == "content_block_delta":
                                    delta = data.get("delta", {})
                                    delta_type = delta.get("type", "")
                                    if delta_type == "text_delta":
                                        token = delta.get("text", "")
                                        if token:
                                            if first_token_time is None:
                                                first_token_time = time.monotonic() - start_time
                                            full_text.append(token)
                                            on_text(token)
                                    elif delta_type == "thinking_delta":
                                        thinking_token = delta.get("thinking", "")
                                        if thinking_token and on_thinking:
                                            on_thinking(thinking_token)
                                elif event_type == "message_start":
                                    usage.input_tokens = data.get("message", {}).get("usage", {}).get("input_tokens", 0)
                                elif event_type == "message_delta":
                                    usage.output_tokens = data.get("usage", {}).get("output_tokens", 0)

                    usage.model = target_model
                    break
                except requests.RequestException as exc:
                    if target_model != FALLBACK_MODEL and "not_found" in str(exc).casefold():
                        continue
                    raise ClaudeClientError(f"Network error connecting to Anthropic API: {exc}") from exc

        now = time.monotonic()
        usage.total_duration = now - start_time
        usage.time_to_first_token = first_token_time or usage.total_duration
        return "".join(full_text), usage

