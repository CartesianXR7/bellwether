"""Tests for AnthropicAdapter. Mocks the SDK client; no real API calls."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from bellwether.protocols import ProviderAdapter, ProviderResponse
from bellwether.providers.anthropic import AnthropicAdapter


def _mock_response(text: str, stop_reason: str, in_tokens: int, out_tokens: int) -> SimpleNamespace:
    return SimpleNamespace(
        content=[SimpleNamespace(text=text)],
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=in_tokens, output_tokens=out_tokens),
    )


def test_adapter_satisfies_protocol():
    client = MagicMock()
    a = AnthropicAdapter("anthropic", "claude-sonnet-4-6", client=client)
    assert isinstance(a, ProviderAdapter)
    assert a.provider_id == "anthropic"
    assert a.model_id == "claude-sonnet-4-6"


def test_call_success_returns_normalized_response():
    client = MagicMock()
    client.messages.create.return_value = _mock_response("The answer is 42.", "end_turn", 100, 20)
    a = AnthropicAdapter("anthropic", "claude-sonnet-4-6", client=client)

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
    client.messages.create.return_value = _mock_response("x", "end_turn", 1, 1)
    a = AnthropicAdapter("anthropic", "claude-sonnet-4-6", client=client)

    a.call("p", max_tokens=512)

    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["temperature"] == 0.0
    assert kwargs["model"] == "claude-sonnet-4-6"
    assert kwargs["max_tokens"] == 512


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("end_turn", "stop"),
        ("max_tokens", "length"),
        ("stop_sequence", "stop"),
        ("tool_use", "tool_use"),
        ("refusal", "content_filter"),
    ],
)
def test_finish_reason_normalization(raw, expected):
    client = MagicMock()
    client.messages.create.return_value = _mock_response("x", raw, 1, 1)
    a = AnthropicAdapter("anthropic", "claude-sonnet-4-6", client=client)
    result = a.call("p", max_tokens=1)
    assert result.finish_reason == expected


def test_call_catches_sdk_exception_and_surfaces_as_error():
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("rate_limit_exceeded")
    a = AnthropicAdapter("anthropic", "claude-sonnet-4-6", client=client)

    result = a.call("p", max_tokens=1024)

    assert result.output_text == ""
    assert result.input_tokens == 0
    assert result.output_tokens == 0
    assert result.finish_reason is None
    assert result.error is not None
    assert "RuntimeError" in result.error
    assert "rate_limit_exceeded" in result.error


def test_call_concatenates_multiple_text_blocks():
    """Anthropic responses are lists of content blocks; we concatenate text blocks."""
    client = MagicMock()
    response = SimpleNamespace(
        content=[SimpleNamespace(text="Part 1 "), SimpleNamespace(text="Part 2.")],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )
    client.messages.create.return_value = response
    a = AnthropicAdapter("anthropic", "claude-sonnet-4-6", client=client)
    result = a.call("p", max_tokens=1024)
    assert result.output_text == "Part 1 Part 2."
