"""Cost guardrail: hard cap on total spend per benchmark run.

The runner consults the tracker before each attempt and halts further calls
once the cap is reached. Untouched instances are recorded as skipped in the
results so the partial leaderboard is still useful (and honest about which
instances were not benched).

Notes on guarantees:
- Tripping is a post-charge check. The runner can therefore overshoot the cap
  by at most one attempt's cost: charge happens, then the next iteration sees
  tripped == True and stops. For a $10 cap and ~$0.05 per attempt, overshoot
  is bounded at ~$0.05.
- The guardrail is per-run, not per-month. Persistent budgets are out of scope.
"""

from __future__ import annotations


class CostExceeded(Exception):
    """Raised when callers explicitly assert there is budget remaining."""


class CostTracker:
    """Tracks accumulated spend; gates further calls via the guardrail."""

    def __init__(self, max_usd: float) -> None:
        if max_usd <= 0:
            raise ValueError(f"max_usd must be positive, got {max_usd}")
        self.max_usd = max_usd
        self.spent_usd = 0.0

    @property
    def tripped(self) -> bool:
        """True once spent_usd reaches max_usd. Equality counts as tripped."""
        return self.spent_usd >= self.max_usd

    @property
    def remaining_usd(self) -> float:
        """Clamped to 0; can't go negative even if charge overshot the cap."""
        return max(0.0, self.max_usd - self.spent_usd)

    def charge(self, cost_usd: float) -> None:
        if cost_usd < 0:
            raise ValueError(f"cost_usd must be non-negative, got {cost_usd}")
        self.spent_usd += cost_usd

    def assert_has_budget(self) -> None:
        if self.tripped:
            raise CostExceeded(
                f"cost guardrail tripped: spent ${self.spent_usd:.4f} >= ${self.max_usd:.4f} cap"
            )

    def __repr__(self) -> str:
        return f"CostTracker(spent=${self.spent_usd:.4f}, max=${self.max_usd:.4f})"
