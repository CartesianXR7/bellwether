"""Tests for GoogleAdapter (Gemini). Mocks the SDK client; no real API calls."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from bellwether.protocols import ProviderAdapter, ProviderResponse
from bellwether.providers.google import GoogleAdapter


def _mock_response(
    text: str, finish_name: str, prompt_tokens: int, completion_tokens: int
) -> SimpleNamespace:
    """Build a SimpleNamespace shaped like a google-genai GenerateContentResponse."""
    finish_enum = SimpleNamespace(name=finish_name) if finish_name else None
    candidate = SimpleNamespace(finish_reason=finish_enum)
    usage = SimpleNamespace(
        prompt_token_count=prompt_tokens, candidates_token_count=completion_tokens
    )
    return SimpleNamespace(text=text, candidates=[candidate], usage_metadata=usage)


def test_adapter_satisfies_protocol():
    client = MagicMock()
    a = GoogleAdapter("google", "gemini-2.0-flash-001", client=client)
    assert isinstance(a, ProviderAdapter)
    assert a.provider_id == "google"
    assert a.model_id == "gemini-2.0-flash-001"


def test_call_success_returns_normalized_response():
    client = MagicMock()
    client.models.generate_content.return_value = _mock_response(
        "The answer is 42.", "STOP", 100, 20
    )
    a = GoogleAdapter("google", "gemini-2.0-flash-001", client=client)

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
    client.models.generate_content.return_value = _mock_response("x", "STOP", 1, 1)
    a = GoogleAdapter("google", "gemini-2.0-flash-001", client=client)

    a.call("p", max_tokens=512)

    kwargs = client.models.generate_content.call_args.kwargs
    assert kwargs["model"] == "gemini-2.0-flash-001"
    assert kwargs["contents"] == "p"
    config = kwargs["config"]
    assert config.temperature == 0.0
    assert config.max_output_tokens == 512


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("STOP", "stop"),
        ("MAX_TOKENS", "length"),
        ("SAFETY", "content_filter"),
        ("RECITATION", "content_filter"),
        ("BLOCKLIST", "content_filter"),
        ("PROHIBITED_CONTENT", "content_filter"),
        ("OTHER", "stop"),
        ("MALFORMED_FUNCTION_CALL", "tool_use"),
    ],
)
def test_finish_reason_normalization(raw, expected):
    client = MagicMock()
    client.models.generate_content.return_value = _mock_response("x", raw, 1, 1)
    a = GoogleAdapter("google", "gemini-2.0-flash-001", client=client)
    result = a.call("p", max_tokens=1)
    assert result.finish_reason == expected


def test_call_catches_sdk_exception_and_surfaces_as_error():
    client = MagicMock()
    client.models.generate_content.side_effect = RuntimeError("quota_exceeded")
    a = GoogleAdapter("google", "gemini-2.0-flash-001", client=client)

    result = a.call("p", max_tokens=1024)

    assert result.output_text == ""
    assert result.error is not None
    assert "RuntimeError" in result.error
    assert "quota_exceeded" in result.error


def test_call_handles_empty_candidates():
    """When a response is fully blocked, candidates can be empty; tokens must
    still be recoverable from usage_metadata."""
    client = MagicMock()
    response = SimpleNamespace(
        text="",
        candidates=[],
        usage_metadata=SimpleNamespace(prompt_token_count=10, candidates_token_count=0),
    )
    client.models.generate_content.return_value = response
    a = GoogleAdapter("google", "gemini-2.0-flash-001", client=client)
    result = a.call("p", max_tokens=1024)
    assert result.output_text == ""
    assert result.input_tokens == 10
    assert result.finish_reason is None
