"""Tests for the function-call routing task."""

from __future__ import annotations

import json

from bellwether.tasks.function_call_routing import FunctionCallRoutingTask
from bellwether.taxonomy import FailureMode


def test_dataset_loader_is_deterministic_with_same_seed():
    t1 = FunctionCallRoutingTask(n_instances=8, seed=42)
    t2 = FunctionCallRoutingTask(n_instances=8, seed=42)
    items1 = list(t1.dataset_loader())
    items2 = list(t2.dataset_loader())
    assert len(items1) == len(items2) == 8
    for a, b in zip(items1, items2, strict=True):
        assert a.instance_id == b.instance_id
        assert a.prompt_inputs == b.prompt_inputs
        assert a.ground_truth == b.ground_truth


def test_dataset_loader_yields_n_instances():
    t = FunctionCallRoutingTask(n_instances=3, seed=7)
    assert len(list(t.dataset_loader())) == 3


def test_dataset_version_includes_seed_and_n():
    t = FunctionCallRoutingTask(n_instances=10, seed=3)
    assert "seed3" in t.dataset_version
    assert "n10" in t.dataset_version


def test_instance_has_tool_and_arguments_in_ground_truth():
    t = FunctionCallRoutingTask(n_instances=5, seed=42)
    for example in t.dataset_loader():
        assert "tool" in example.ground_truth
        assert "arguments" in example.ground_truth
        assert isinstance(example.ground_truth["arguments"], dict)


def test_validator_passes_on_exact_match():
    t = FunctionCallRoutingTask(n_instances=1, seed=42)
    [example] = list(t.dataset_loader())
    output = json.dumps(example.ground_truth)
    result = t.validator(output, example.ground_truth)
    assert result.passed
    assert result.score == 1.0


def test_validator_schema_break_on_missing_fields():
    t = FunctionCallRoutingTask(n_instances=1, seed=42)
    [example] = list(t.dataset_loader())
    output = json.dumps({"tool": "get_weather"})  # missing 'arguments'
    result = t.validator(output, example.ground_truth)
    assert not result.passed
    assert FailureMode.SCHEMA_BREAK in result.failure_modes


def test_validator_schema_break_on_arguments_not_dict():
    t = FunctionCallRoutingTask(n_instances=1, seed=42)
    [example] = list(t.dataset_loader())
    output = json.dumps({"tool": "get_weather", "arguments": ["x", "y"]})
    result = t.validator(output, example.ground_truth)
    assert not result.passed
    assert FailureMode.SCHEMA_BREAK in result.failure_modes


def test_validator_partial_when_tool_correct_but_args_wrong():
    t = FunctionCallRoutingTask(n_instances=1, seed=42)
    [example] = list(t.dataset_loader())
    output = json.dumps(
        {"tool": example.ground_truth["tool"], "arguments": {"wrong": "args"}}
    )
    result = t.validator(output, example.ground_truth)
    assert not result.passed
    assert result.score == 0.5
    assert FailureMode.PARTIAL in result.failure_modes


def test_validator_confabulation_when_wrong_tool():
    t = FunctionCallRoutingTask(n_instances=1, seed=42)
    [example] = list(t.dataset_loader())
    output = json.dumps({"tool": "definitely_not_a_real_tool", "arguments": {}})
    result = t.validator(output, example.ground_truth)
    assert not result.passed
    assert result.score == 0.0
    assert FailureMode.CONFABULATION in result.failure_modes


def test_validator_failure_reason_does_not_leak_ground_truth():
    """METHODOLOGY s3: failure_reason must not echo expected values or
    quote ground truth (the tool registry is in the prompt, but specific
    chosen tool/argument values for this instance must not appear)."""
    t = FunctionCallRoutingTask(n_instances=1, seed=42)
    [example] = list(t.dataset_loader())
    output = json.dumps({"tool": "get_stock_price", "arguments": {"ticker": "WRONG"}})
    result = t.validator(output, example.ground_truth)
    assert result.failure_reason is not None
    # Note: the expected tool name might or might not be in the failure reason
    # depending on which tool was chosen; we check that ARGUMENT VALUES from
    # ground_truth (the leak risk) do not appear.
    for arg_value in example.ground_truth["arguments"].values():
        assert str(arg_value) not in result.failure_reason, (
            f"failure_reason leaks ground-truth value: {arg_value!r}"
        )
    # Score should not appear (would tell the model how close it was).
    assert "0.5" not in result.failure_reason
    assert "50%" not in result.failure_reason
