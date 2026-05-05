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


def test_pricing_table_has_v0_entries():
    """v0 ships with one model per provider populated. Verify shape, not values
    (values themselves need human verification against provider pricing pages
    before publish; see comment in pricing.py)."""
    expected_keys = {
        ("anthropic", "claude-sonnet-4-6"),
        ("openai", "gpt-4o"),
        ("google", "gemini-2.0-flash-001"),
    }
    assert set(PRICING_TABLE.keys()) == expected_keys
    for key, entry in PRICING_TABLE.items():
        assert entry.input_per_million_usd > 0, f"{key} input price must be positive"
        assert entry.output_per_million_usd > 0, f"{key} output price must be positive"
        assert entry.as_of, f"{key} missing as_of date"
        assert entry.source_url.startswith("http"), f"{key} source_url must be a URL"
