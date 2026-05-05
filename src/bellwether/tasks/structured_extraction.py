"""Task #1: structured-output extraction from synthetic invoices.

Deterministic, license-free, fastest signal across providers. The generator
uses a fixed seed to produce identical invoice text across runs; combined with
T=0 on the providers, this is the closest we get to byte-stable benchmarking
(though not a guarantee per METHODOLOGY s7).

Validator parses the model's JSON output and exact-matches each required field
against ground truth. failure_reason is constrained to schema/format level
only per METHODOLOGY s3 (no echoing expected values, no field-value diffs,
no quoted ground truth in any form).
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from typing import Any, Iterable

from bellwether.protocols import Example, ValidationResult
from bellwether.taxonomy import FailureMode

_REQUIRED_FIELDS = ("invoice_number", "date", "vendor", "total_usd")

_VENDORS = (
    "Acme Corporation",
    "Globex Inc.",
    "Initech LLC",
    "Umbrella Holdings",
    "Stark Industries",
    "Wayne Enterprises",
    "Soylent Corp",
    "Cyberdyne Systems",
)

_CANONICAL_PROMPT = """Extract the following fields from the invoice below into a single JSON object.

Required fields:
- invoice_number (string)
- date (string in YYYY-MM-DD format)
- vendor (string)
- total_usd (number)

Output ONLY the JSON object. No prose, no code fences, no commentary.

Invoice:
{invoice_text}
"""


@dataclass
class StructuredExtractionTask:
    """Synthetic invoice extraction. Implements bellwether.protocols.Task structurally."""

    name: str = "structured_extraction"
    description: str = (
        "Extract structured fields (invoice_number, date, vendor, total_usd) "
        "from a synthetic invoice into a JSON object. Deterministic, license-free."
    )
    canonical_prompt_template: str = _CANONICAL_PROMPT
    tuned_prompt_templates: dict[str, str] = field(default_factory=dict)
    max_attempts: int = 3
    timeout_seconds: int = 30
    pass_threshold: float = 1.0
    license: str = "synthetic-no-redistribution-required"
    n_instances: int = 5
    seed: int = 42

    @property
    def dataset_version(self) -> str:
        """Reproducible identifier; same seed + n produces identical instances."""
        return f"synthetic-invoice-v1-seed{self.seed}-n{self.n_instances}"

    def dataset_loader(self) -> Iterable[Example]:
        rng = random.Random(self.seed)
        for i in range(self.n_instances):
            invoice_number = f"INV-{1000 + i:04d}"
            year = 2026
            month = rng.randint(1, 12)
            day = rng.randint(1, 28)
            date = f"{year}-{month:02d}-{day:02d}"
            vendor = rng.choice(_VENDORS)
            total = round(rng.uniform(100.0, 10000.0), 2)

            invoice_text = (
                "INVOICE\n"
                "==================\n"
                f"Number: {invoice_number}\n"
                f"Date:   {date}\n"
                f"Vendor: {vendor}\n"
                f"Total:  ${total:.2f}\n"
                "==================\n"
            )
            yield Example(
                instance_id=invoice_number,
                prompt_inputs={"invoice_text": invoice_text},
                ground_truth={
                    "invoice_number": invoice_number,
                    "date": date,
                    "vendor": vendor,
                    "total_usd": total,
                },
            )

    def validator(self, output: str, ground_truth: Any) -> ValidationResult:
        parsed = _parse_json_object(output)
        if isinstance(parsed, _ParseError):
            return ValidationResult(
                passed=False,
                score=0.0,
                failure_reason=parsed.message,
                failure_modes=[FailureMode.SCHEMA_BREAK],
            )

        missing = [f for f in _REQUIRED_FIELDS if f not in parsed]
        if missing:
            # Schema-level: missing field NAMES are part of the prompt, not ground truth.
            return ValidationResult(
                passed=False,
                score=0.0,
                failure_reason=f"missing required field(s): {', '.join(missing)}",
                failure_modes=[FailureMode.SCHEMA_BREAK],
            )

        n_correct = sum(
            1 for f in _REQUIRED_FIELDS if _field_matches(parsed[f], ground_truth[f])
        )
        score = n_correct / len(_REQUIRED_FIELDS)

        if score >= self.pass_threshold:
            return ValidationResult(passed=True, score=score)

        # Per s3: do NOT name which fields were wrong, do NOT echo expected
        # values, do NOT quote ground truth. Generic message only.
        return ValidationResult(
            passed=False,
            score=score,
            failure_reason="field values did not match expected ground truth",
            failure_modes=(
                [FailureMode.PARTIAL] if score > 0 else [FailureMode.CONFABULATION]
            ),
        )


@dataclass
class _ParseError:
    message: str


def _parse_json_object(output: str) -> dict[str, Any] | _ParseError:
    """Parse JSON, tolerating leading/trailing whitespace.

    Does NOT extract JSON from markdown code fences or surrounding prose. The
    canonical prompt instructs "ONLY the JSON object," so a model that wraps
    in fences fails s3 (output format). That is a real failure to record.
    """
    stripped = output.strip()
    if not stripped:
        return _ParseError("output is empty")
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        return _ParseError(
            f"json parse error at line {exc.lineno} col {exc.colno}: {exc.msg}"
        )
    if not isinstance(parsed, dict):
        return _ParseError(f"expected JSON object, got {type(parsed).__name__}")
    return parsed


def _field_matches(actual: Any, expected: Any) -> bool:
    """Exact match for strings; tolerate float vs int for numerics."""
    if isinstance(expected, float) and isinstance(actual, (int, float)):
        return abs(float(actual) - expected) < 1e-9
    return actual == expected
