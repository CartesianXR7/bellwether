"""Failure-mode taxonomy per METHODOLOGY s5.

Eight categories. Multiple modes per failure are allowed (e.g. CONFABULATION
plus PARTIAL, or REFUSAL plus TRUNCATION). Empty list means validation passed.

Per s5: in v0, OFFTASK collapses into CONFABULATION because v0 datasets do not
ship per-instance "expected key entities" annotations needed to distinguish
them. Classifiers default to CONFABULATION for content failures.
"""

from __future__ import annotations

import re
from enum import Enum


class FailureMode(str, Enum):
    REFUSAL = "refusal"
    CONFABULATION = "confabulation"
    SCHEMA_BREAK = "schema_break"
    TRUNCATION = "truncation"
    OFFTASK = "offtask"
    PARTIAL = "partial"
    TIMEOUT = "timeout"
    ERROR = "error"


REFUSAL_PATTERNS: tuple[str, ...] = (
    r"\bI can(?:'?t| ?not)\b",
    r"\bI(?:'m| am) (?:not (?:able|allowed)|unable)\b",
    r"\bI won(?:'?t| ?not)\b",
    r"\b(?:as|being) an? (?:AI|language model|assistant)\b",
    r"\bI(?:'m| am) sorry,? (?:but )?I (?:can(?:'?t| ?not)|won(?:'?t| ?not))\b",
    r"\bagainst (?:my|the) (?:guidelines|policy|policies)\b",
    r"\bI (?:cannot|will not|am unable to) (?:assist|help|comply|provide|generate)\b",
)

_REFUSAL_REGEX = re.compile("|".join(REFUSAL_PATTERNS), re.IGNORECASE)


def looks_like_refusal(output: str) -> bool:
    """Best-effort regex match against common refusal phrases.

    This signal is only meaningful when validation also fails. A response
    that passes validation is not a refusal even if it matches the regex
    (e.g. an extraction that contains "I can't" inside quoted source text).
    The runner unions this signal into failure_modes only on failure.
    """
    return bool(_REFUSAL_REGEX.search(output))


def looks_like_truncation(output: str, finish_reason: str | None) -> bool:
    """Best-effort truncation detection.

    Two signals: provider-reported finish_reason == "length", or output ends
    with an alphanumeric character with no terminal punctuation (mid-word
    cutoff). The second signal is brittle for outputs that legitimately end
    in alphanumerics (e.g. JSON fragments); validators with structured outputs
    should rely on schema parse failure (SCHEMA_BREAK) instead.
    """
    if finish_reason == "length":
        return True
    stripped = output.rstrip()
    if not stripped:
        return False
    return stripped[-1].isalnum()


def derive_runtime_failure_modes(
    *,
    output: str,
    finish_reason: str | None,
    timed_out: bool,
    api_error: str | None,
) -> list[FailureMode]:
    """Classify failures from runtime signals (provider, response shape).

    Validator-derived modes (SCHEMA_BREAK, PARTIAL, CONFABULATION, OFFTASK)
    come from ValidationResult.failure_modes. The runner unions those with
    what this function returns to produce the final InstanceResult.failure_modes.

    ERROR and TIMEOUT short-circuit and dominate; the rest stack additively.
    """
    if api_error is not None:
        return [FailureMode.ERROR]
    if timed_out:
        return [FailureMode.TIMEOUT]

    modes: list[FailureMode] = []
    if looks_like_truncation(output, finish_reason):
        modes.append(FailureMode.TRUNCATION)
    if looks_like_refusal(output):
        modes.append(FailureMode.REFUSAL)
    return modes
