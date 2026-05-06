"""Tests for the structured-extraction task (synthetic invoice)."""

from __future__ import annotations

import json

from bellwether.tasks.structured_extraction import StructuredExtractionTask
from bellwether.taxonomy import FailureMode


def test_dataset_loader_is_deterministic_with_same_seed():
    t1 = StructuredExtractionTask(n_instances=5, seed=42)
    t2 = StructuredExtractionTask(n_instances=5, seed=42)
    items1 = list(t1.dataset_loader())
    items2 = list(t2.dataset_loader())
    assert len(items1) == len(items2) == 5
    for a, b in zip(items1, items2, strict=True):
        assert a.instance_id == b.instance_id
        assert a.prompt_inputs == b.prompt_inputs
        assert a.ground_truth == b.ground_truth


def test_dataset_loader_differs_with_different_seed():
    t1 = StructuredExtractionTask(n_instances=5, seed=42)
    t2 = StructuredExtractionTask(n_instances=5, seed=99)
    items1 = list(t1.dataset_loader())
    items2 = list(t2.dataset_loader())
    # Vendors and totals should diverge between seeds; comparing all fields
    # element-wise should produce at least one mismatch.
    assert any(
        a.ground_truth != b.ground_truth for a, b in zip(items1, items2, strict=True)
    )


def test_dataset_version_includes_seed_and_n():
    t = StructuredExtractionTask(n_instances=10, seed=7)
    assert "seed7" in t.dataset_version
    assert "n10" in t.dataset_version


def test_dataset_loader_yields_n_instances():
    t = StructuredExtractionTask(n_instances=3, seed=42)
    assert len(list(t.dataset_loader())) == 3


def test_instance_has_required_ground_truth_fields():
    t = StructuredExtractionTask(n_instances=1, seed=42)
    [example] = list(t.dataset_loader())
    for f in ("invoice_number", "date", "vendor", "total_usd"):
        assert f in example.ground_truth


def test_validator_passes_on_exact_match():
    t = StructuredExtractionTask(n_instances=1, seed=42)
    [example] = list(t.dataset_loader())
    output = json.dumps(example.ground_truth)
    result = t.validator(output, example.ground_truth)
    assert result.passed
    assert result.score == 1.0
    assert result.failure_modes == []


def test_validator_passes_with_surrounding_whitespace():
    t = StructuredExtractionTask(n_instances=1, seed=42)
    [example] = list(t.dataset_loader())
    output = "  \n" + json.dumps(example.ground_truth) + "\n  "
    result = t.validator(output, example.ground_truth)
    assert result.passed


def test_validator_schema_break_on_invalid_json():
    t = StructuredExtractionTask(n_instances=1, seed=42)
    [example] = list(t.dataset_loader())
    result = t.validator("not json at all", example.ground_truth)
    assert not result.passed
    assert FailureMode.SCHEMA_BREAK in result.failure_modes
    assert "json parse error" in (result.failure_reason or "")


def test_validator_schema_break_on_non_object_json():
    t = StructuredExtractionTask(n_instances=1, seed=42)
    [example] = list(t.dataset_loader())
    result = t.validator("[1, 2, 3]", example.ground_truth)
    assert not result.passed
    assert FailureMode.SCHEMA_BREAK in result.failure_modes


def test_validator_schema_break_on_missing_fields():
    t = StructuredExtractionTask(n_instances=1, seed=42)
    [example] = list(t.dataset_loader())
    output = json.dumps({"invoice_number": "INV-1000"})  # missing 3 of 4 required fields
    result = t.validator(output, example.ground_truth)
    assert not result.passed
    assert FailureMode.SCHEMA_BREAK in result.failure_modes
    assert "missing required field" in (result.failure_reason or "")


def test_validator_schema_break_on_empty_output():
    t = StructuredExtractionTask(n_instances=1, seed=42)
    [example] = list(t.dataset_loader())
    result = t.validator("", example.ground_truth)
    assert not result.passed
    assert FailureMode.SCHEMA_BREAK in result.failure_modes


def test_validator_partial_on_some_correct_some_wrong():
    t = StructuredExtractionTask(n_instances=1, seed=42)
    [example] = list(t.dataset_loader())
    output = dict(example.ground_truth)
    output["vendor"] = "Wrong Corp"  # 3 of 4 right
    result = t.validator(json.dumps(output), example.ground_truth)
    assert not result.passed
    assert result.score == 0.75
    assert FailureMode.PARTIAL in result.failure_modes


def test_validator_confabulation_on_all_wrong_values():
    t = StructuredExtractionTask(n_instances=1, seed=42)
    [example] = list(t.dataset_loader())
    output = {
        "invoice_number": "WRONG",
        "date": "2099-12-31",
        "vendor": "Nobody",
        "total_usd": -1.0,
    }
    result = t.validator(json.dumps(output), example.ground_truth)
    assert not result.passed
    assert result.score == 0.0
    assert FailureMode.CONFABULATION in result.failure_modes


def test_validator_failure_reason_does_not_leak_ground_truth():
    """METHODOLOGY s3: failure_reason must not echo expected values, name
    missing entities (other than schema fields), or quote ground truth."""
    t = StructuredExtractionTask(n_instances=1, seed=42)
    [example] = list(t.dataset_loader())
    output = dict(example.ground_truth)
    output["vendor"] = "Wrong Corp"
    result = t.validator(json.dumps(output), example.ground_truth)

    assert result.failure_reason is not None
    expected_vendor = example.ground_truth["vendor"]
    expected_invoice = example.ground_truth["invoice_number"]
    expected_date = example.ground_truth["date"]
    # Forbidden: actual expected values must NOT appear in the retry hint.
    assert expected_vendor not in result.failure_reason
    assert expected_invoice not in result.failure_reason
    assert expected_date not in result.failure_reason
    # Score values should not appear (would tell the model how close it is).
    assert "0.75" not in result.failure_reason
    assert "75%" not in result.failure_reason


def test_validator_total_usd_tolerates_int_vs_float():
    t = StructuredExtractionTask(n_instances=1, seed=42)
    [example] = list(t.dataset_loader())
    gt = dict(example.ground_truth)
    gt["total_usd"] = 100.0
    output = dict(gt)
    output["total_usd"] = 100  # int not float
    result = t.validator(json.dumps(output), gt)
    assert result.passed
