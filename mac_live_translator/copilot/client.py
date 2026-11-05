"""Claude Haiku 5.5 streaming client using the official Anthropic Python SDK."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Callable

import anthropic

from mac_live_translator.config import CLAUDE_MODEL


@dataclass
class ClaudeUsage:
    """Usage and latency statistics for an executed Claude request."""
    input_tokens: int = 0
    output_tokens: int = 0
    time_to_first_token: float = 0.0
    total_duration: float = 0.0
    context_prep_duration: float = 0.0
    model: str = CLAUDE_MODEL


class ClaudeClientError(Exception):
    """Base exception for Claude API failures."""
    pass


class ClaudeClient:
    """Client for Anthropic Claude models with streaming, thinking delta separation, and cancellation."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = CLAUDE_MODEL,
        max_tokens: int = 2048,
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
        """Stream a chat request to Claude using the official Anthropic SDK."""
        if not self.is_configured():
            raise ClaudeClientError(
                "Anthropic API key is not configured. Please enter your key in the Copilot tab."
            )

        client = anthropic.Anthropic(api_key=self.api_key)
        start_time = time.monotonic()
        if on_request_start:
            on_request_start()

        full_text: list[str] = []
        first_token_time: float | None = None
        usage = ClaudeUsage(model=self.model)

        try:
            with client.messages.stream(
                model=self.model,
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

        except anthropic.AuthenticationError as exc:
            raise ClaudeClientError("Invalid Anthropic API Key (401 Unauthorized).") from exc
        except anthropic.RateLimitError as exc:
            raise ClaudeClientError("Anthropic rate limit reached (429). Please retry shortly.") from exc
        except anthropic.NotFoundError as exc:
            raise ClaudeClientError(
                f"Anthropic model '{self.model}' not found (404). Please verify model name."
            ) from exc
        except anthropic.APIStatusError as exc:
            raise ClaudeClientError(f"Anthropic API error ({exc.status_code}): {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise ClaudeClientError(f"Network error connecting to Anthropic API: {exc}") from exc
        except Exception as exc:
            raise ClaudeClientError(f"Anthropic SDK error: {exc}") from exc

        now = time.monotonic()
        usage.total_duration = now - start_time
        usage.time_to_first_token = first_token_time or usage.total_duration
        return "".join(full_text), usage

