"""Tests for pricing and cost computation."""

from __future__ import annotations

import dataclasses

import pytest

from bellwether.pricing import PRICING_TABLE, Pricing, cost_for, lookup


def _pricing(input_per_m: float = 3.0, output_per_m: float = 15.0) -> Pricing:
    return Pricing(
        provider="test",
        model="test-model",
        input_per_million_usd=input_per_m,
        output_per_million_usd=output_per_m,
        as_of="2026-05-05",
        source_url="https://example.test/pricing",
    )


def test_cost_for_zero_tokens():
    assert cost_for(_pricing(), 0, 0) == 0.0


def test_cost_for_one_million_input_tokens():
    p = _pricing(input_per_m=3.0, output_per_m=15.0)
    assert cost_for(p, 1_000_000, 0) == pytest.approx(3.0)


def test_cost_for_one_million_output_tokens():
    p = _pricing(input_per_m=3.0, output_per_m=15.0)
    assert cost_for(p, 0, 1_000_000) == pytest.approx(15.0)


def test_cost_for_typical_attempt():
    """1500 input + 800 output at Sonnet-shaped pricing ($3 / $15 per million)."""
    p = _pricing(input_per_m=3.0, output_per_m=15.0)
    expected = (1500 / 1_000_000 * 3.0) + (800 / 1_000_000 * 15.0)
    assert cost_for(p, 1500, 800) == pytest.approx(expected)


def test_pricing_is_frozen():
    p = _pricing()
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.input_per_million_usd = 99.0  # type: ignore[misc]


def test_lookup_raises_for_missing_entry():
    with pytest.raises(KeyError) as excinfo:
        lookup("not_a_provider", "not_a_model")
    assert "not_a_provider" in str(excinfo.value)
    assert "not_a_model" in str(excinfo.value)


def test_pricing_table_has_v0_4_entries():
    """v0.4 ships 27 entries across 6 providers (3 anthropic + 5 openai +
    3 google + 4 xai + 4 perplexity + 8 openrouter). Verify shape, not values
    (values are verified against provider pricing pages and the LiteLLM
    catalog; see comment block at the top of pricing.py)."""
    expected_keys = {
        # Anthropic
        ("anthropic", "claude-sonnet-4-6"),
        ("anthropic", "claude-haiku-4-5"),
        ("anthropic", "claude-opus-4-7"),
        # OpenAI (standard + o-series reasoning)
        ("openai", "gpt-4o"),
        ("openai", "gpt-4o-mini"),
        ("openai", "o3"),
        ("openai", "o3-mini"),
        ("openai", "o4-mini"),
        # Google
        ("google", "gemini-2.5-flash-lite"),
        ("google", "gemini-2.5-flash"),
        ("google", "gemini-2.5-pro"),
        # xAI Grok
        ("xai", "grok-4"),
        ("xai", "grok-4-fast"),
        ("xai", "grok-3"),
        ("xai", "grok-3-mini"),
        # Perplexity Sonar
        ("perplexity", "sonar"),
        ("perplexity", "sonar-pro"),
        ("perplexity", "sonar-reasoning"),
        ("perplexity", "sonar-reasoning-pro"),
        # OpenRouter
        ("openrouter", "meta-llama/llama-4-maverick"),
        ("openrouter", "meta-llama/llama-4-scout"),
        ("openrouter", "meta-llama/llama-3.3-70b-instruct"),
        ("openrouter", "deepseek/deepseek-chat"),
        ("openrouter", "deepseek/deepseek-r1"),
        ("openrouter", "mistralai/mistral-large"),
        ("openrouter", "cohere/command-r-plus"),
        ("openrouter", "qwen/qwen-3-235b-a22b"),
    }
    assert set(PRICING_TABLE.keys()) == expected_keys
    distinct_providers = {k[0] for k in PRICING_TABLE}
    assert distinct_providers == {
        "anthropic",
        "openai",
        "google",
        "xai",
        "perplexity",
        "openrouter",
    }
    for key, entry in PRICING_TABLE.items():
        assert entry.input_per_million_usd > 0, f"{key} input price must be positive"
        assert entry.output_per_million_usd > 0, f"{key} output price must be positive"
        assert entry.as_of, f"{key} missing as_of date"
        assert entry.source_url.startswith("http"), f"{key} source_url must be a URL"
        assert entry.model_class in {"standard", "reasoning", "search"}, (
            f"{key} has unrecognized model_class={entry.model_class!r}"
        )


def test_pricing_table_reasoning_models_classified():
    """v0.4 / methodology v0.1.1: reasoning models must carry
    model_class='reasoning' so the leaderboard does not silently rank them
    against standard chat models on the same effective_TCoT scale.
    See METHODOLOGY s2.7."""
    expected_reasoning = {
        ("openai", "o3"),
        ("openai", "o3-mini"),
        ("openai", "o4-mini"),
        ("perplexity", "sonar-reasoning"),
        ("perplexity", "sonar-reasoning-pro"),
        ("openrouter", "deepseek/deepseek-r1"),
    }
    actual_reasoning = {
        key for key, entry in PRICING_TABLE.items() if entry.model_class == "reasoning"
    }
    assert actual_reasoning == expected_reasoning


def test_pricing_table_search_models_classified():
    """v0.4 / methodology v0.1.1: search-augmented (Perplexity Sonar) models
    must carry model_class='search'. Reasoning Sonar variants are 'reasoning',
    not 'search'. See METHODOLOGY s2.7."""
    expected_search = {
        ("perplexity", "sonar"),
        ("perplexity", "sonar-pro"),
    }
    actual_search = {key for key, entry in PRICING_TABLE.items() if entry.model_class == "search"}
    assert actual_search == expected_search


def test_pricing_table_default_model_class_is_standard():
    """Entries that omit model_class default to 'standard'. The Anthropic and
    Google entries below were authored before v0.1.1 and rely on the default."""
    assert PRICING_TABLE[("anthropic", "claude-sonnet-4-6")].model_class == "standard"
    assert PRICING_TABLE[("google", "gemini-2.5-flash-lite")].model_class == "standard"
    assert PRICING_TABLE[("openai", "gpt-4o")].model_class == "standard"


def test_output_pricing_at_least_input_pricing_for_paid_tier():
    """Sanity: every modern API charges at least as much for output tokens as
    input. If a row inverts, that is almost certainly a paste error in the
    table. (Equality is permitted; some open-weights providers price both
    sides the same.)"""
    for key, entry in PRICING_TABLE.items():
        assert entry.output_per_million_usd >= entry.input_per_million_usd, (
            f"{key}: output ({entry.output_per_million_usd}) cheaper than "
            f"input ({entry.input_per_million_usd}); paste error?"
        )
