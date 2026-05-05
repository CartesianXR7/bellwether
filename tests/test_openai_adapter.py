"""Tests for OpenAIAdapter. Mocks the SDK client; no real API calls."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from bellwether.protocols import ProviderAdapter, ProviderResponse
from bellwether.providers.openai import OpenAIAdapter


def _mock_response(
    content: str,
    finish_reason: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> SimpleNamespace:
    choice = SimpleNamespace(
        message=SimpleNamespace(content=content),
        finish_reason=finish_reason,
    )
    usage = SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    return SimpleNamespace(choices=[choice], usage=usage)


def test_adapter_satisfies_protocol():
    client = MagicMock()
    a = OpenAIAdapter("openai", "gpt-4o", client=client)
    assert isinstance(a, ProviderAdapter)
    assert a.provider_id == "openai"
    assert a.model_id == "gpt-4o"


def test_call_success_returns_normalized_response():
    client = MagicMock()
    client.chat.completions.create.return_value = _mock_response(
        "The answer is 42.", "stop", 100, 20
    )
    a = OpenAIAdapter("openai", "gpt-4o", client=client)

    result = a.call("test prompt", max_tokens=1024)

    assert isinstance(result, ProviderResponse)
    assert result.output_text == "The answer is 42."
    assert result.input_tokens == 100
    assert result.output_tokens == 20
    assert result.finish_reason == "stop"
    assert result.error is None
    assert result.latency_seconds >= 0


def test_call_passes_temperature_zero_and_model_id():
    client = MagicMock()
    client.chat.completions.create.return_value = _mock_response("x", "stop", 1, 1)
    a = OpenAIAdapter("openai", "gpt-4o", client=client)

    a.call("p", max_tokens=512)

    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["temperature"] == 0.0
    assert kwargs["model"] == "gpt-4o"
    assert kwargs["max_tokens"] == 512


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("stop", "stop"),
        ("length", "length"),
        ("content_filter", "content_filter"),
        ("tool_calls", "tool_use"),
        ("function_call", "tool_use"),
    ],
)
def test_finish_reason_normalization(raw, expected):
    client = MagicMock()
    client.chat.completions.create.return_value = _mock_response("x", raw, 1, 1)
    a = OpenAIAdapter("openai", "gpt-4o", client=client)
    result = a.call("p", max_tokens=1)
    assert result.finish_reason == expected


def test_call_catches_sdk_exception_and_surfaces_as_error():
    client = MagicMock()
    client.chat.completions.create.side_effect = RuntimeError("invalid_api_key")
    a = OpenAIAdapter("openai", "gpt-4o", client=client)

    result = a.call("p", max_tokens=1024)

    assert result.output_text == ""
    assert result.error is not None
    assert "RuntimeError" in result.error
    assert "invalid_api_key" in result.error


def test_call_handles_none_content():
    """OpenAI returns content=None when the choice is filtered or empty; we coerce to ''."""
    client = MagicMock()
    choice = SimpleNamespace(
        message=SimpleNamespace(content=None),
        finish_reason="content_filter",
    )
    response = SimpleNamespace(
        choices=[choice], usage=SimpleNamespace(prompt_tokens=10, completion_tokens=0)
    )
    client.chat.completions.create.return_value = response
    a = OpenAIAdapter("openai", "gpt-4o", client=client)
    result = a.call("p", max_tokens=1024)
    assert result.output_text == ""
    assert result.finish_reason == "content_filter"
