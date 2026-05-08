"""OpenAI adapter for GPT models.

Wraps the official `openai` SDK. finish_reason is largely already normalized
("stop", "length", "content_filter", "tool_calls"); we map "tool_calls" to
"tool_use" for cross-provider consistency.
"""

from __future__ import annotations

import os
import re
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

# OpenAI's o-series reasoning models (o1, o3, o4-mini, etc.) reject
# `temperature` set to anything other than the default 1, and require
# `max_completion_tokens` rather than `max_tokens`. Detect by the leading
# 'o<digit>' pattern, which covers o1/o3/o4 families without false-matching
# legacy 'gpt-4o' (which is not a reasoning model). This is OpenAI-proper
# only; OpenAI-compatible vendors (xAI, Perplexity, OpenRouter) accept the
# normal params transparently even for their own reasoning models.
_OPENAI_REASONING_RE = re.compile(r"^o\d")


def _is_openai_reasoning(provider_id: str, model_id: str) -> bool:
    return provider_id == "openai" and bool(_OPENAI_REASONING_RE.match(model_id))


class OpenAIAdapter:
    """Adapter for OpenAI-compatible Chat Completions APIs.

    Used directly for OpenAI proper, and parameterized via base_url +
    api_key_env_var for other OpenAI-compatible services (xAI Grok at
    api.x.ai, Perplexity Sonar at api.perplexity.ai, OpenRouter at
    openrouter.ai/api/v1, etc.). The wire protocol is identical; only
    the endpoint and credential source differ.
    """

    def __init__(
        self,
        provider_id: str,
        model_id: str,
        api_key: str | None = None,
        client: Any | None = None,
        base_url: str | None = None,
        api_key_env_var: str = "OPENAI_API_KEY",
    ) -> None:
        self.provider_id = provider_id
        self.model_id = model_id
        if client is not None:
            self._client = client
        else:
            from openai import OpenAI

            key = api_key or os.environ.get(api_key_env_var)
            client_kwargs: dict[str, Any] = {"api_key": key}
            if base_url:
                client_kwargs["base_url"] = base_url
            self._client = OpenAI(**client_kwargs)

    def call(self, prompt: str, max_tokens: int) -> ProviderResponse:
        start = time.monotonic()
        kwargs: dict[str, Any] = {
            "model": self.model_id,
            "messages": [{"role": "user", "content": prompt}],
        }
        if _is_openai_reasoning(self.provider_id, self.model_id):
            # o-series: reject `temperature != 1` and `max_tokens`; use
            # `max_completion_tokens` instead.
            kwargs["max_completion_tokens"] = max_tokens
        else:
            kwargs["max_tokens"] = max_tokens
            kwargs["temperature"] = 0.0
        try:
            resp = self._client.chat.completions.create(**kwargs)
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
