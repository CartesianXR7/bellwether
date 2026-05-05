"""Anthropic adapter for Claude models.

Wraps the official `anthropic` SDK. Catches all SDK errors and surfaces them
via ProviderResponse.error so the runner can classify as FailureMode.ERROR
without losing the latency observation from the failed attempt.
"""

from __future__ import annotations

import os
import time
from typing import Any

from bellwether.protocols import ProviderResponse

# Anthropic stop_reason -> normalized finish_reason vocabulary.
_FINISH_MAP = {
    "end_turn": "stop",
    "max_tokens": "length",
    "stop_sequence": "stop",
    "tool_use": "tool_use",
    "refusal": "content_filter",
}


class AnthropicAdapter:
    """Adapter for Anthropic Messages API. Supports Claude Sonnet/Haiku/Opus."""

    def __init__(
        self,
        provider_id: str,
        model_id: str,
        api_key: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.provider_id = provider_id
        self.model_id = model_id
        if client is not None:
            self._client = client
        else:
            from anthropic import Anthropic

            self._client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    def call(self, prompt: str, max_tokens: int) -> ProviderResponse:
        start = time.monotonic()
        try:
            resp = self._client.messages.create(
                model=self.model_id,
                max_tokens=max_tokens,
                temperature=0.0,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            # Broad catch: SDK error hierarchy varies by version; the runner
            # treats anything here as FailureMode.ERROR. Internal bugs would
            # also be swallowed, but they will surface in unit tests rather
            # than mid-bench.
            return ProviderResponse(
                output_text="",
                input_tokens=0,
                output_tokens=0,
                finish_reason=None,
                latency_seconds=time.monotonic() - start,
                error=f"{type(exc).__name__}: {exc}",
            )

        latency = time.monotonic() - start
        text = "".join(getattr(block, "text", "") for block in resp.content)
        raw_stop = resp.stop_reason or ""
        return ProviderResponse(
            output_text=text,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            finish_reason=_FINISH_MAP.get(raw_stop, raw_stop or None),
            latency_seconds=latency,
            error=None,
        )
