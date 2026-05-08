"""Total Cost of Task (TCoT) per METHODOLOGY s2.

Headline metric is `effective_TCoT`: total spend per successful completion,
including the cost of failed attempts amortized across the successes.

The naive shorthand `mean_TCoT_success / success_rate` undercounts because it
implicitly assumes mean_TCoT_failure == mean_TCoT_success, which is rarely
true (failures usually consume all max_attempts; successes often pass on
attempt 1). The corrected formula is equivalent to:

    total_spend_across_all_instances / num_successes
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import mean, median, quantiles, stdev

from bellwether.taxonomy import FailureMode


@dataclass
class Attempt:
    """One attempt's observations.

    cost_usd is computed by the runner from pricing + token counts at attempt
    time; storing it here keeps the per-instance TCoT a pure sum, no pricing
    table lookup required at aggregation time.
    """

    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_seconds: float


@dataclass
class InstanceResult:
    """Outcome for one task instance after up to max_attempts retries."""

    instance_id: str
    attempts: list[Attempt]
    succeeded: bool
    failure_modes: list[FailureMode] = field(default_factory=list)

    @property
    def tcot(self) -> float:
        """Sum of attempt costs (METHODOLOGY s2.1)."""
        return sum(a.cost_usd for a in self.attempts)

    def __post_init__(self) -> None:
        if self.succeeded and self.failure_modes:
            raise ValueError(
                f"InstanceResult {self.instance_id!r}: succeeded=True but "
                f"failure_modes is non-empty ({self.failure_modes}). "
                f"A successful instance has no failure modes."
            )
        if not self.succeeded and not self.failure_modes:
            raise ValueError(
                f"InstanceResult {self.instance_id!r}: succeeded=False but "
                f"failure_modes is empty. Per METHODOLOGY s5 every failure "
                f"must be classified into at least one mode (the runner "
                f"defaults to CONFABULATION for unclassified content failures)."
            )
        if not self.attempts:
            raise ValueError(
                f"InstanceResult {self.instance_id!r}: attempts is empty. "
                f"Even an immediate ERROR/TIMEOUT records the attempted call."
            )


@dataclass(frozen=True)
class AggregateMetrics:
    """Per (provider x task) aggregates over N instances. METHODOLOGY s2.3.

    std fields are population stddev across the per-trial observations.
    Per s7, mean +/- std reporting acknowledges that T=0 does not guarantee
    determinism. std == 0.0 when there are fewer than 2 observations of the
    relevant kind (cannot compute stddev; reported as 0 rather than NaN).
    """

    n_instances: int
    n_successes: int
    success_rate: float
    mean_tcot_success: float
    mean_tcot_failure: float
    effective_tcot: float
    mean_latency_p50: float
    mean_latency_p95: float
    std_tcot_success: float
    std_latency: float


def effective_tcot(
    mean_tcot_success: float,
    mean_tcot_failure: float,
    success_rate: float,
) -> float:
    """METHODOLOGY s2.3 corrected formula.

    effective_TCoT = mean_TCoT_success + mean_TCoT_failure * (1 - success_rate) / success_rate

    Equivalent to total_spend_across_all_instances / num_successes.

    Returns +inf when success_rate == 0 (no successes, undefined cost-per-success).
    """
    if success_rate < 0 or success_rate > 1:
        raise ValueError(f"success_rate must be in [0, 1], got {success_rate}")
    if success_rate == 0:
        return math.inf
    return mean_tcot_success + mean_tcot_failure * (1 - success_rate) / success_rate


def _p95(values: list[float]) -> float:
    """95th percentile, inclusive method. Returns 0.0 for empty input."""
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return quantiles(values, n=100, method="inclusive")[94]


def _std_or_zero(values: list[float]) -> float:
    """Population stddev; returns 0.0 if fewer than 2 samples (avoids NaN)."""
    if len(values) < 2:
        return 0.0
    return stdev(values)


def aggregate(results: list[InstanceResult]) -> AggregateMetrics:
    """Aggregate per-instance results into headline metrics. METHODOLOGY s2.3."""
    if not results:
        raise ValueError("aggregate requires at least one InstanceResult")

    successes = [r for r in results if r.succeeded]
    failures = [r for r in results if not r.succeeded]
    n = len(results)
    n_succ = len(successes)
    success_rate = n_succ / n

    success_costs = [r.tcot for r in successes]
    failure_costs = [r.tcot for r in failures]
    mean_succ = mean(success_costs) if success_costs else 0.0
    mean_fail = mean(failure_costs) if failure_costs else 0.0
    std_succ = _std_or_zero(success_costs)
    eff = effective_tcot(mean_succ, mean_fail, success_rate)

    latencies = [a.latency_seconds for r in results for a in r.attempts]
    p50 = median(latencies) if latencies else 0.0
    p95 = _p95(latencies)
    std_lat = _std_or_zero(latencies)

    return AggregateMetrics(
        n_instances=n,
        n_successes=n_succ,
        success_rate=success_rate,
        mean_tcot_success=mean_succ,
        mean_tcot_failure=mean_fail,
        effective_tcot=eff,
        mean_latency_p50=p50,
        mean_latency_p95=p95,
        std_tcot_success=std_succ,
        std_latency=std_lat,
    )
