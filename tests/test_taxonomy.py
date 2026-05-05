"""Tests for failure-mode taxonomy classifiers. METHODOLOGY s5."""

from __future__ import annotations

import pytest

from bellwether.taxonomy import (
    FailureMode,
    derive_runtime_failure_modes,
    looks_like_refusal,
    looks_like_truncation,
)


# ---- looks_like_refusal ----


@pytest.mark.parametrize(
    "text",
    [
        "I can't help with that.",
        "I cannot assist with this request.",
        "As an AI, I'm not able to provide this information.",
        "I'm sorry, but I can't comply with that request.",
        "That goes against my guidelines.",
        "I won't help with that.",
        "I am unable to generate that content.",
    ],
)
def test_looks_like_refusal_matches_common_phrases(text):
    assert looks_like_refusal(text)


@pytest.mark.parametrize(
    "text",
    [
        "Here is the answer: 42.",
        "The capital of France is Paris.",
        '{"invoice_number": "INV-001"}',
        "",
    ],
)
def test_looks_like_refusal_does_not_match_normal_output(text):
    assert not looks_like_refusal(text)


# ---- looks_like_truncation ----


def test_looks_like_truncation_finish_reason_length():
    assert looks_like_truncation("any output", finish_reason="length")


def test_looks_like_truncation_mid_word_cutoff():
    assert looks_like_truncation("The quick brown fo", finish_reason="stop")


def test_looks_like_truncation_clean_termination_with_period():
    assert not looks_like_truncation("The answer is 42.", finish_reason="stop")


def test_looks_like_truncation_clean_termination_with_punctuation():
    assert not looks_like_truncation("Answer: complete.", finish_reason="stop")


def test_looks_like_truncation_json_close_brace():
    assert not looks_like_truncation('{"k": "v"}', finish_reason="stop")


def test_looks_like_truncation_empty_output():
    assert not looks_like_truncation("", finish_reason="stop")
    assert not looks_like_truncation("   ", finish_reason="stop")


# ---- derive_runtime_failure_modes ----


def test_derive_modes_api_error_dominates():
    modes = derive_runtime_failure_modes(
        output="anything",
        finish_reason="stop",
        timed_out=False,
        api_error="rate_limit_exceeded",
    )
    assert modes == [FailureMode.ERROR]


def test_derive_modes_timeout_dominates_when_no_api_error():
    modes = derive_runtime_failure_modes(
        output="partial...",
        finish_reason=None,
        timed_out=True,
        api_error=None,
    )
    assert modes == [FailureMode.TIMEOUT]


def test_derive_modes_api_error_takes_priority_over_timeout():
    modes = derive_runtime_failure_modes(
        output="",
        finish_reason=None,
        timed_out=True,
        api_error="connection_reset",
    )
    assert modes == [FailureMode.ERROR]


def test_derive_modes_truncation_alone():
    modes = derive_runtime_failure_modes(
        output="Here is the answ",
        finish_reason="length",
        timed_out=False,
        api_error=None,
    )
    assert FailureMode.TRUNCATION in modes
    assert FailureMode.REFUSAL not in modes


def test_derive_modes_refusal_alone():
    modes = derive_runtime_failure_modes(
        output="I can't help with that.",
        finish_reason="stop",
        timed_out=False,
        api_error=None,
    )
    assert FailureMode.REFUSAL in modes
    assert FailureMode.TRUNCATION not in modes


def test_derive_modes_both_truncation_and_refusal_possible():
    """Multi-mode classification per s5: a truncated refusal counts as both."""
    modes = derive_runtime_failure_modes(
        output="I'm sorry but I can't help with this and the response was cu",
        finish_reason="length",
        timed_out=False,
        api_error=None,
    )
    assert FailureMode.TRUNCATION in modes
    assert FailureMode.REFUSAL in modes


def test_derive_modes_clean_output_returns_empty():
    """Runtime-derived modes are empty for clean output. Validator-derived modes
    (CONFABULATION, SCHEMA_BREAK, PARTIAL) come from ValidationResult."""
    modes = derive_runtime_failure_modes(
        output="The answer is 42.",
        finish_reason="stop",
        timed_out=False,
        api_error=None,
    )
    assert modes == []
