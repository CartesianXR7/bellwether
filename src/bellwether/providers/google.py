"""Google adapter for Gemini models.

Wraps the new `google-genai` SDK (NOT the older `google-generativeai`).
Designed for AI Studio API keys (AIza... format); also works with Vertex
when GOOGLE_GENAI_USE_VERTEXAI=true is set in the environment.
"""

from __future__ import annotations

import os
import time
from typing import Any

from bellwether.protocols import ProviderResponse

# Gemini FinishReason enum names -> normalized vocabulary.
_FINISH_MAP = {
    "STOP": "stop",
    "MAX_TOKENS": "length",
    "SAFETY": "content_filter",
    "RECITATION": "content_filter",
    "BLOCKLIST": "content_filter",
    "PROHIBITED_CONTENT": "content_filter",
    "SPII": "content_filter",
    "LANGUAGE": "stop",
    "OTHER": "stop",
    "MALFORMED_FUNCTION_CALL": "tool_use",
    "FINISH_REASON_UNSPECIFIED": None,
}


class GoogleAdapter:
    """Adapter for Google Gemini via google-genai SDK."""

    def __init__(
        self,
        provider_id: str,
        model_id: str,
        api_key: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.provider_id = provider_id
        self.model_id = model_id
        self._api_key = api_key or os.environ.get("GOOGLE_API_KEY")
        # Optional injected client (tests). If provided, reused across calls.
        # In production we construct a fresh client per call to work around a
        # google-genai 1.75 bug where tenacity-driven retries can close the
        # underlying httpx client and leave subsequent calls failing with
        # "Cannot send a request, as the client has been closed."
        self._injected_client = client

    def _get_client(self) -> Any:
        if self._injected_client is not None:
            return self._injected_client
        from google import genai

        return genai.Client(api_key=self._api_key)

    def call(self, prompt: str, max_tokens: int) -> ProviderResponse:
        from google.genai import types

        client = self._get_client()
        start = time.monotonic()
        try:
            resp = client.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=max_tokens,
                ),
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
        candidate = resp.candidates[0] if resp.candidates else None
        raw_finish = candidate.finish_reason if candidate else None
        finish_name = raw_finish.name if raw_finish is not None else None
        usage = resp.usage_metadata
        return ProviderResponse(
            output_text=resp.text or "",
            input_tokens=usage.prompt_token_count if usage else 0,
            output_tokens=usage.candidates_token_count if usage else 0,
            finish_reason=_FINISH_MAP.get(finish_name, finish_name) if finish_name else None,
            latency_seconds=latency,
            error=None,
        )
