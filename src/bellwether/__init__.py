"""bellwether: cost-and-failure-mode benchmark for LLM agents.

See METHODOLOGY.md for formulas, validator contract, and reproducibility rules.
"""

__version__ = "0.3.0"
__methodology_version__ = "0.1"

from bellwether.guardrail import CostExceeded, CostTracker
from bellwether.pricing import PRICING_TABLE, PRICING_VERSION, Pricing, cost_for, lookup
from bellwether.protocols import (
    Example,
    ProviderAdapter,
    ProviderResponse,
    Task,
    ValidationResult,
)
from bellwether.taxonomy import (
    FailureMode,
    derive_runtime_failure_modes,
    looks_like_refusal,
    looks_like_truncation,
)
from bellwether.tcot import (
    AggregateMetrics,
    Attempt,
    InstanceResult,
    aggregate,
    effective_tcot,
)

__all__ = [
    "PRICING_TABLE",
    "PRICING_VERSION",
    "AggregateMetrics",
    "Attempt",
    "CostExceeded",
    "CostTracker",
    "Example",
    "FailureMode",
    "InstanceResult",
    "Pricing",
    "ProviderAdapter",
    "ProviderResponse",
    "Task",
    "ValidationResult",
    "__methodology_version__",
    "__version__",
    "aggregate",
    "cost_for",
    "derive_runtime_failure_modes",
    "effective_tcot",
    "looks_like_refusal",
    "looks_like_truncation",
    "lookup",
]
