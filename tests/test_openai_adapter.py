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


def test_call_for_openai_reasoning_models_uses_max_completion_tokens_no_temperature():
    """OpenAI o-series (o1/o3/o4) reject temperature != 1 and require
    max_completion_tokens instead of max_tokens. Verify the adapter switches
    to that calling convention only for openai/o<digit> models, not for
    gpt-4o (which is a standard chat model despite the leading 'o' in 'gpt-4o')
    and not for OpenAI-compatible vendors that route their own reasoning models.
    """
    client = MagicMock()
    client.chat.completions.create.return_value = _mock_response("ok", "stop", 5, 5)
    a = OpenAIAdapter("openai", "o3", client=client)

    a.call("p", max_tokens=512)

    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "o3"
    assert kwargs["max_completion_tokens"] == 512
    assert "max_tokens" not in kwargs
    assert "temperature" not in kwargs


def test_call_for_openai_compatible_reasoning_uses_normal_params():
    """OpenAI-compatible vendors (Perplexity, OpenRouter routing DeepSeek R1)
    accept the normal temperature + max_tokens convention even for their own
    reasoning models. The o-series carve-out is OpenAI-proper only."""
    client = MagicMock()
    client.chat.completions.create.return_value = _mock_response("ok", "stop", 5, 5)
    a = OpenAIAdapter("openrouter", "deepseek/deepseek-r1", client=client)

    a.call("p", max_tokens=512)

    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["max_tokens"] == 512
    assert kwargs["temperature"] == 0.0


def test_adapter_accepts_base_url_for_openai_compatible_services(monkeypatch):
    """v0.4: OpenAIAdapter is parameterized so the same class works for any
    OpenAI-compatible HTTPS endpoint (xAI, Perplexity, OpenRouter). The
    adapter must read the API key from the named env var (NOT OPENAI_API_KEY)
    and pass base_url through to the underlying SDK client.
    """
    captured: dict[str, object] = {}

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setenv("XAI_API_KEY", "xai-test-key-9999")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("openai.OpenAI", _FakeOpenAI)

    OpenAIAdapter(
        provider_id="xai",
        model_id="grok-4",
        base_url="https://api.x.ai/v1",
        api_key_env_var="XAI_API_KEY",
    )

    assert captured["base_url"] == "https://api.x.ai/v1"
    assert captured["api_key"] == "xai-test-key-9999"
