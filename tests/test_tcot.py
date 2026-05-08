"""Tests for TCoT formulas and aggregation. METHODOLOGY s2."""

from __future__ import annotations

import math

import pytest

from bellwether.taxonomy import FailureMode
from bellwether.tcot import Attempt, InstanceResult, aggregate, effective_tcot


def _attempt(cost: float = 0.001, latency: float = 0.1) -> Attempt:
    return Attempt(input_tokens=100, output_tokens=50, cost_usd=cost, latency_seconds=latency)


# ---- effective_tcot formula correctness (METHODOLOGY s2.3) ----


def test_effective_tcot_all_successes_equals_mean_success_cost():
    # success_rate = 1.0 zeroes the failure term regardless of mean_TCoT_failure.
    assert effective_tcot(0.002, 999.0, 1.0) == pytest.approx(0.002)


def test_effective_tcot_no_successes_is_infinite():
    assert math.isinf(effective_tcot(0.0, 0.001, 0.0))


def test_effective_tcot_worked_example_from_methodology_s2_3():
    """Provider A: 100% success at $0.002.
    Provider B: 50% success at $0.001/success, $0.003 burned per failure.
    """
    a = effective_tcot(mean_tcot_success=0.002, mean_tcot_failure=0.0, success_rate=1.0)
    b = effective_tcot(mean_tcot_success=0.001, mean_tcot_failure=0.003, success_rate=0.5)
    assert a == pytest.approx(0.002)
    assert b == pytest.approx(0.004)
    assert b > a, "Reliability + asymmetric failure cost makes B worse than A."


def test_effective_tcot_corrected_formula_exceeds_naive_when_failures_costlier():
    """The naive shorthand `mean_TCoT_success / success_rate` undercounts when
    mean_TCoT_failure > mean_TCoT_success. This is the typical case (failures
    consume all max_attempts; successes often pass on attempt 1)."""
    mean_succ = 0.001
    mean_fail = 0.003
    success_rate = 0.5
    naive = mean_succ / success_rate
    corrected = effective_tcot(mean_succ, mean_fail, success_rate)
    assert corrected > naive


def test_effective_tcot_equals_naive_when_failure_cost_equals_success_cost():
    """Sanity: when per-instance costs are symmetric, corrected matches naive."""
    cost = 0.001
    sr = 0.5
    assert effective_tcot(cost, cost, sr) == pytest.approx(cost / sr)


@pytest.mark.parametrize("sr", [-0.1, 1.5, 2.0])
def test_effective_tcot_rejects_invalid_success_rate(sr):
    with pytest.raises(ValueError):
        effective_tcot(0.001, 0.001, sr)


# ---- InstanceResult invariants ----


def test_instance_result_tcot_sums_attempt_costs():
    r = InstanceResult(
        instance_id="x",
        attempts=[_attempt(0.001), _attempt(0.002), _attempt(0.003)],
        succeeded=True,
    )
    assert r.tcot == pytest.approx(0.006)


def test_instance_result_rejects_succeeded_with_failure_modes():
    with pytest.raises(ValueError):
        InstanceResult(
            instance_id="x",
            attempts=[_attempt()],
            succeeded=True,
            failure_modes=[FailureMode.PARTIAL],
        )


def test_instance_result_rejects_failure_with_no_modes():
    """Per METHODOLOGY s5, every failure has at least one mode."""
    with pytest.raises(ValueError):
        InstanceResult(instance_id="x", attempts=[_attempt()], succeeded=False)


def test_instance_result_rejects_no_attempts():
    """Even an immediate error records the attempted call."""
    with pytest.raises(ValueError):
        InstanceResult(instance_id="x", attempts=[], succeeded=True)


# ---- aggregate ----


def test_aggregate_empty_raises():
    with pytest.raises(ValueError):
        aggregate([])


def test_aggregate_all_successes():
    results = [
        InstanceResult("a", [_attempt(0.001)], True),
        InstanceResult("b", [_attempt(0.002)], True),
        InstanceResult("c", [_attempt(0.003)], True),
    ]
    m = aggregate(results)
    assert m.n_instances == 3
    assert m.n_successes == 3
    assert m.success_rate == pytest.approx(1.0)
    assert m.mean_tcot_success == pytest.approx(0.002)
    assert m.mean_tcot_failure == pytest.approx(0.0)
    assert m.effective_tcot == pytest.approx(0.002)
    # std of [0.001, 0.002, 0.003] = 0.001
    assert m.std_tcot_success == pytest.approx(0.001)


def test_aggregate_std_zero_for_single_observation():
    results = [InstanceResult("only", [_attempt(0.001)], True)]
    m = aggregate(results)
    assert m.std_tcot_success == 0.0
    assert m.std_latency == 0.0


def test_aggregate_std_latency_computed_across_attempts():
    """std_latency aggregates ALL attempts, not just trial means."""
    results = [
        InstanceResult("a", [Attempt(0, 0, 0.0, 1.0), Attempt(0, 0, 0.0, 2.0)], True),
        InstanceResult("b", [Attempt(0, 0, 0.0, 3.0)], True),
    ]
    m = aggregate(results)
    # latencies = [1.0, 2.0, 3.0]; population stddev = 1.0
    assert m.std_latency == pytest.approx(1.0)


def test_aggregate_mixed_with_asymmetric_failure_cost():
    """Two successes at $0.001 (1 attempt each), two failures at $0.003 (3 attempts each).

    Total spend = 2 * 0.001 + 2 * 0.003 = 0.008.
    Successes = 2.
    Total spend / successes = 0.004 -> matches effective_tcot.
    """
    results = [
        InstanceResult("s1", [_attempt(0.001)], True),
        InstanceResult("s2", [_attempt(0.001)], True),
        InstanceResult(
            "f1",
            [_attempt(0.001), _attempt(0.001), _attempt(0.001)],
            False,
            failure_modes=[FailureMode.CONFABULATION],
        ),
        InstanceResult(
            "f2",
            [_attempt(0.001), _attempt(0.001), _attempt(0.001)],
            False,
            failure_modes=[FailureMode.CONFABULATION],
        ),
    ]
    m = aggregate(results)
    assert m.n_instances == 4
    assert m.n_successes == 2
    assert m.success_rate == pytest.approx(0.5)
    assert m.mean_tcot_success == pytest.approx(0.001)
    assert m.mean_tcot_failure == pytest.approx(0.003)
    assert m.effective_tcot == pytest.approx(0.004)
    # Cross-check the equivalence: total_spend / num_successes = 0.008 / 2 = 0.004.
    total_spend = sum(r.tcot for r in results)
    assert m.effective_tcot == pytest.approx(total_spend / m.n_successes)


def test_aggregate_no_successes_returns_inf_effective_tcot():
    results = [
        InstanceResult("f1", [_attempt(0.001)], False, [FailureMode.REFUSAL]),
        InstanceResult("f2", [_attempt(0.002)], False, [FailureMode.REFUSAL]),
    ]
    m = aggregate(results)
    assert m.n_successes == 0
    assert m.success_rate == 0.0
    assert math.isinf(m.effective_tcot)


def test_aggregate_latency_percentiles():
    results = [
        InstanceResult(f"i{i}", [Attempt(0, 0, 0.0, float(i))], True) for i in range(1, 101)
    ]
    m = aggregate(results)
    assert m.mean_latency_p50 == pytest.approx(50.5)
    assert 94 < m.mean_latency_p95 < 96
