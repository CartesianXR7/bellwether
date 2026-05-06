"""Task and ProviderAdapter Protocols per METHODOLOGY s8.

Implementations satisfy the structural typing without inheriting from Protocol.
Defaults shown in the methodology spec (max_attempts=3, timeout_seconds=30,
pass_threshold=1.0) are documentation for implementers; Protocol attributes
themselves do not carry default values.

The methodology spec writes dataset_loader and validator as Callable attributes;
declaring them as methods on the Protocol is structurally equivalent and
preferred for readability.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from bellwether.taxonomy import FailureMode

ProviderId = str


@dataclass
class Example:
    """One task instance. dataset_loader yields these."""

    instance_id: str
    prompt_inputs: dict[str, Any]
    ground_truth: Any
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """Per METHODOLOGY s4. pass_threshold lives on Task, not here.

    failure_reason is constrained to schema/format level only per s3. Validators
    that emit content-level reasons (expected values, named missing entities,
    F1 deltas, quoted ground truth) leak ground truth into the retry loop and
    invalidate the run.
    """

    passed: bool
    score: float
    failure_reason: str | None = None
    failure_modes: list[FailureMode] = field(default_factory=list)


@dataclass
class ProviderResponse:
    """One attempt's output from a ProviderAdapter.

    cost_usd is computed by the runner from pricing + token counts, not by the
    adapter, so the same adapter can be re-priced if needed.
    """

    output_text: str
    input_tokens: int
    output_tokens: int
    finish_reason: str | None
    latency_seconds: float
    error: str | None = None


@runtime_checkable
class Task(Protocol):
    """Per METHODOLOGY s8. Runner refuses to bench tasks that fail this contract."""

    name: str
    description: str
    dataset_version: str
    canonical_prompt_template: str
    tuned_prompt_templates: dict[ProviderId, str]
    max_attempts: int
    timeout_seconds: int
    pass_threshold: float
    license: str

    def dataset_loader(self) -> Iterable[Example]: ...

    def validator(self, output: str, ground_truth: Any) -> ValidationResult: ...


@runtime_checkable
class ProviderAdapter(Protocol):
    """Adapter for a single provider/model.

    `call` blocks until the provider returns a response or raises. Network and
    rate-limit errors should be caught and surfaced via `ProviderResponse.error`
    rather than propagated, so the runner can classify them as FailureMode.ERROR
    without losing token-count or latency observations from prior partial work.
    """

    provider_id: str
    model_id: str

    def call(self, prompt: str, max_tokens: int) -> ProviderResponse: ...
