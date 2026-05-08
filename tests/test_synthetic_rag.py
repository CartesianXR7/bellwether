"""Tests for the synthetic RAG (single-fact retrieval) task."""

from __future__ import annotations

from bellwether.tasks.synthetic_rag import SyntheticRagTask
from bellwether.taxonomy import FailureMode


def test_dataset_loader_is_deterministic_with_same_seed():
    t1 = SyntheticRagTask(n_instances=5, seed=42)
    t2 = SyntheticRagTask(n_instances=5, seed=42)
    items1 = list(t1.dataset_loader())
    items2 = list(t2.dataset_loader())
    assert len(items1) == len(items2) == 5
    for a, b in zip(items1, items2, strict=True):
        assert a.instance_id == b.instance_id
        assert a.prompt_inputs == b.prompt_inputs
        assert a.ground_truth == b.ground_truth


def test_dataset_version_includes_seed_and_n():
    t = SyntheticRagTask(n_instances=10, seed=7)
    assert "seed7" in t.dataset_version
    assert "n10" in t.dataset_version


def test_instance_has_passage_and_question():
    t = SyntheticRagTask(n_instances=1, seed=42)
    [example] = list(t.dataset_loader())
    assert "passage" in example.prompt_inputs
    assert "question" in example.prompt_inputs
    assert example.ground_truth in example.prompt_inputs["passage"], (
        "ground-truth answer must appear verbatim in the passage; otherwise "
        "the task is unanswerable from the passage alone"
    )


def test_validator_passes_on_exact_match():
    t = SyntheticRagTask(n_instances=1, seed=42)
    [example] = list(t.dataset_loader())
    result = t.validator(example.ground_truth, example.ground_truth)
    assert result.passed
    assert result.score == 1.0


def test_validator_passes_with_surrounding_whitespace():
    t = SyntheticRagTask(n_instances=1, seed=42)
    [example] = list(t.dataset_loader())
    result = t.validator(f"  {example.ground_truth}  ", example.ground_truth)
    assert result.passed


def test_validator_passes_with_trailing_period():
    t = SyntheticRagTask(n_instances=1, seed=42)
    [example] = list(t.dataset_loader())
    result = t.validator(f"{example.ground_truth}.", example.ground_truth)
    assert result.passed


def test_validator_passes_with_quotes():
    t = SyntheticRagTask(n_instances=1, seed=42)
    [example] = list(t.dataset_loader())
    result = t.validator(f'"{example.ground_truth}"', example.ground_truth)
    assert result.passed


def test_validator_passes_case_insensitive():
    t = SyntheticRagTask(n_instances=1, seed=42)
    [example] = list(t.dataset_loader())
    result = t.validator(str(example.ground_truth).upper(), example.ground_truth)
    assert result.passed


def test_validator_schema_break_on_empty():
    t = SyntheticRagTask(n_instances=1, seed=42)
    [example] = list(t.dataset_loader())
    result = t.validator("", example.ground_truth)
    assert not result.passed
    assert FailureMode.SCHEMA_BREAK in result.failure_modes


def test_validator_confabulation_on_wrong_answer():
    t = SyntheticRagTask(n_instances=1, seed=42)
    [example] = list(t.dataset_loader())
    result = t.validator("definitely-not-the-answer-12345", example.ground_truth)
    assert not result.passed
    assert FailureMode.CONFABULATION in result.failure_modes


def test_validator_failure_reason_does_not_leak_ground_truth():
    """METHODOLOGY s3: failure_reason must not echo the expected answer."""
    t = SyntheticRagTask(n_instances=1, seed=42)
    [example] = list(t.dataset_loader())
    result = t.validator("wrong answer", example.ground_truth)
    assert result.failure_reason is not None
    assert str(example.ground_truth) not in result.failure_reason, (
        f"failure_reason leaks ground-truth answer: {example.ground_truth!r}"
    )
