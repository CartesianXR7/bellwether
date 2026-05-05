"""OpenAI adapter for GPT models.

Wraps the official `openai` SDK. finish_reason is largely already normalized
("stop", "length", "content_filter", "tool_calls"); we map "tool_calls" to
"tool_use" for cross-provider consistency.
"""

from __future__ import annotations

import os
import time
from typing import Any

from bellwether.protocols import ProviderResponse

_FINISH_MAP = {
    "stop": "stop",
    "length": "length",
    "content_filter": "content_filter",
    "tool_calls": "tool_use",
    "function_call": "tool_use",
}


class OpenAIAdapter:
    """Adapter for OpenAI Chat Completions API."""

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
            from openai import OpenAI

            self._client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))

    def call(self, prompt: str, max_tokens: int) -> ProviderResponse:
        start = time.monotonic()
        try:
            resp = self._client.chat.completions.create(
                model=self.model_id,
                max_tokens=max_tokens,
                temperature=0.0,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            return ProviderResponse(
                output_text="",
                input_tokens=0,
                output_tokens=0,
                finish_reason=None,
                latency_seconds=time.monotonic() - start,
                error=f"{type(exc).__name__}: {exc}",
            )

        latency = time.monotonic() - start
        choice = resp.choices[0]
        raw_finish = choice.finish_reason or ""
        return ProviderResponse(
            output_text=choice.message.content or "",
            input_tokens=resp.usage.prompt_tokens,
            output_tokens=resp.usage.completion_tokens,
            finish_reason=_FINISH_MAP.get(raw_finish, raw_finish or None),
            latency_seconds=latency,
            error=None,
        )
