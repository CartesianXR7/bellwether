"""Tests for CostTracker."""

from __future__ import annotations

import pytest

from bellwether.guardrail import CostExceeded, CostTracker


def test_init_rejects_zero():
    with pytest.raises(ValueError):
        CostTracker(0.0)


def test_init_rejects_negative():
    with pytest.raises(ValueError):
        CostTracker(-1.0)


def test_starts_at_zero_spend():
    t = CostTracker(10.0)
    assert t.spent_usd == 0.0
    assert not t.tripped
    assert t.remaining_usd == 10.0


def test_charge_accumulates():
    t = CostTracker(10.0)
    t.charge(0.5)
    t.charge(0.3)
    assert t.spent_usd == pytest.approx(0.8)
    assert not t.tripped
    assert t.remaining_usd == pytest.approx(9.2)


def test_charge_rejects_negative():
    t = CostTracker(10.0)
    with pytest.raises(ValueError):
        t.charge(-0.01)


def test_tripped_at_exact_cap():
    t = CostTracker(1.0)
    t.charge(1.0)
    assert t.tripped
    assert t.remaining_usd == 0.0


def test_tripped_when_exceeded():
    t = CostTracker(1.0)
    t.charge(1.5)
    assert t.tripped
    assert t.remaining_usd == 0.0  # clamped, not negative


def test_assert_has_budget_passes_under_cap():
    t = CostTracker(10.0)
    t.charge(5.0)
    t.assert_has_budget()  # no raise


def test_assert_has_budget_raises_when_tripped():
    t = CostTracker(1.0)
    t.charge(1.5)
    with pytest.raises(CostExceeded):
        t.assert_has_budget()


def test_repr_shows_spend_and_max():
    t = CostTracker(10.0)
    t.charge(2.5)
    r = repr(t)
    assert "2.5000" in r
    assert "10.0000" in r
