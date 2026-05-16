"""Tests for the Critique-Pass evaluation track. METHODOLOGY s13.

Covers:
- CANONICAL_CRITIQUE_PROMPT text is locked. Changes require a methodology version
  bump per s13.2; this test enforces no accidental drift.
- build_critique_followup_prompt composes the second-leg prompt correctly.
- run_task_for_provider with critique_pass=True makes 2 adapter calls per
  attempt; costs, tokens, and latency aggregate; attempt records carry the
  critique sub-object; top-level critique_pass field is present on the result.
- critique_pass=False is byte-equivalent to v0.1.x behavior (regression check).
- Site builder pairs critique-off and critique-on entries into a delta row.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from bellwether.critique import CANONICAL_CRITIQUE_PROMPT, build_critique_followup_prompt
from bellwether.guardrail import CostTracker
from bellwether.protocols import ProviderResponse
from bellwether.runner import run_task_for_provider
from bellwether.tasks.structured_extraction import StructuredExtractionTask


def test_canonical_critique_prompt_text_is_locked():
    """The exact string is the methodology contract. Any change must accompany a
    methodology version bump (s13.2). This test fails loudly if the prompt
    drifts so the bump is not silently skipped.
    """
    expected = (
        "Review your previous answer for correctness and adherence to the requested format. "
        "If it is already correct, repeat it exactly. "
        "If not, output the corrected version. "
        "Output only the final answer with no commentary."
    )
    assert CANONICAL_CRITIQUE_PROMPT == expected


def test_canonical_critique_prompt_has_no_validator_leak():
    """Per s13.5, the canonical critique prompt MUST NOT include the validator's
    checklist, field names, expected values, or rubric. This keeps the track
    blind and prevents ground-truth leak via s3.
    """
    leaked_terms = (
        "invoice_number",
        "vendor",
        "total_usd",
        "json",
        "JSON",
        "schema",
        "ground truth",
    )
    for term in leaked_terms:
        assert term not in CANONICAL_CRITIQUE_PROMPT, (
            f"validator term '{term}' must not leak into the critique prompt"
        )


def test_build_critique_followup_prompt_composes_legs():
    """Second-leg prompt should carry the original prompt, the first-leg output,
    and the canonical critique prompt, in that order.
    """
    original = "Extract X from Y."
    first_leg = '{"x": 1}'
    composed = build_critique_followup_prompt(original, first_leg)
    assert composed.startswith(original)
    assert first_leg in composed
    assert composed.endswith(CANONICAL_CRITIQUE_PROMPT)


def _make_mock_adapter(outputs: list[str], tokens_in: int = 100, tokens_out: int = 50):
    """Mock ProviderAdapter that returns the given outputs one per call.

    Each call returns a ProviderResponse with fixed token counts and latency
    so cost arithmetic is deterministic. provider_id and model_id are set to
    a pricing-table entry so lookup() succeeds in the runner.
    """
    adapter = MagicMock()
    adapter.provider_id = "anthropic"
    adapter.model_id = "claude-sonnet-4-6"
    call_sequence = iter(outputs)

    def _call(prompt: str, max_tokens: int) -> ProviderResponse:
        return ProviderResponse(
            output_text=next(call_sequence),
            input_tokens=tokens_in,
            output_tokens=tokens_out,
            finish_reason="stop",
            latency_seconds=0.1,
            error=None,
        )

    adapter.call.side_effect = _call
    return adapter


def _good_extraction_output(example) -> str:
    """Synthesize the JSON output structured_extraction expects, from a known
    Example. Used to make mock attempts "succeed" so the runner exits early.
    """
    gt = example.ground_truth
    return (
        f'{{"invoice_number": "{gt["invoice_number"]}", '
        f'"date": "{gt["date"]}", '
        f'"vendor": "{gt["vendor"]}", '
        f'"total_usd": {gt["total_usd"]}}}'
    )


def test_critique_pass_off_makes_one_call_per_attempt(tmp_path: Path):
    """Regression: with critique_pass=False the runner must behave exactly as
    v0.1.x. One adapter call per attempt; no `critique` sub-object on records;
    top-level critique_pass=False on the result JSON.
    """
    task = StructuredExtractionTask(n_instances=2, seed=42, max_attempts=1)
    instances = list(task.dataset_loader())
    adapter = _make_mock_adapter([_good_extraction_output(e) for e in instances])

    record = run_task_for_provider(
        task=task,
        adapter=adapter,
        n_runs=1,
        cost_tracker=CostTracker(max_usd=1.0),
        git_sha="deadbeef",
        git_dirty=False,
        repo_dir=tmp_path,
        output_dir=tmp_path,
        critique_pass=False,
    )

    assert record["critique_pass"] is False
    assert adapter.call.call_count == 2  # one per instance, no second leg
    for inst in record["instances"]:
        for run in inst["runs"]:
            for att in run["attempts"]:
                assert "critique" not in att, (
                    "critique sub-object must not appear when critique_pass=False"
                )


def test_critique_pass_on_makes_two_calls_per_attempt(tmp_path: Path):
    """With critique_pass=True, every attempt becomes two adapter calls (leg A
    plus leg B). Validator scores leg B. Cost, tokens, latency aggregate
    across both legs per s13.1.
    """
    task = StructuredExtractionTask(n_instances=2, seed=42, max_attempts=1)
    instances = list(task.dataset_loader())
    # Leg A: bad output (so we can prove leg B is the one validated against).
    # Leg B: correct output. Cost/tokens come from the mock so both legs have
    # identical token counts; the runner should sum them.
    bad = '{"invoice_number": "WRONG"}'
    outputs = []
    for e in instances:
        outputs.append(bad)
        outputs.append(_good_extraction_output(e))
    adapter = _make_mock_adapter(outputs, tokens_in=100, tokens_out=50)

    record = run_task_for_provider(
        task=task,
        adapter=adapter,
        n_runs=1,
        cost_tracker=CostTracker(max_usd=1.0),
        git_sha="deadbeef",
        git_dirty=False,
        repo_dir=tmp_path,
        output_dir=tmp_path,
        critique_pass=True,
    )

    assert record["critique_pass"] is True
    assert adapter.call.call_count == 4  # 2 instances x 2 legs
    for inst in record["instances"]:
        for run in inst["runs"]:
            assert len(run["attempts"]) == 1
            att = run["attempts"][0]
            assert att["input_tokens"] == 200  # 100 (A) + 100 (B)
            assert att["output_tokens"] == 100  # 50 (A) + 50 (B)
            assert math.isclose(att["latency_seconds"], 0.2, rel_tol=1e-9)
            assert att["validation"]["passed"] is True
            assert "critique" in att
            critique = att["critique"]
            assert critique["pre_critique_output"] == bad
            assert critique["pre_critique_input_tokens"] == 100
            assert critique["post_critique_input_tokens"] == 100
            assert critique["critique_skipped_reason"] is None


def test_critique_pass_second_leg_skipped_when_leg_a_errors(tmp_path: Path):
    """If leg A returns an error, leg B is skipped (no useful output to critique).
    Validator runs over leg A. Attempt record's critique sub-object marks
    the skip reason. Only one adapter call is consumed per attempt.
    """
    task = StructuredExtractionTask(n_instances=1, seed=42, max_attempts=1)

    adapter = MagicMock()
    adapter.provider_id = "anthropic"
    adapter.model_id = "claude-sonnet-4-6"
    call_outputs = iter([
        ProviderResponse(
            output_text="",
            input_tokens=0,
            output_tokens=0,
            finish_reason=None,
            latency_seconds=0.05,
            error="rate-limited",
        )
    ])
    adapter.call.side_effect = lambda prompt, max_tokens: next(call_outputs)

    record = run_task_for_provider(
        task=task,
        adapter=adapter,
        n_runs=1,
        cost_tracker=CostTracker(max_usd=1.0),
        git_sha="deadbeef",
        git_dirty=False,
        repo_dir=tmp_path,
        output_dir=tmp_path,
        critique_pass=True,
    )

    # One instance, one attempt, one call (leg A errored, leg B skipped).
    assert adapter.call.call_count == 1
    att = record["instances"][0]["runs"][0]["attempts"][0]
    assert att["error"] == "rate-limited"
    assert att["validation"]["passed"] is False
    assert att["critique"]["critique_skipped_reason"] == "leg_a_error_or_cost_guardrail"
    assert att["critique"]["post_critique_input_tokens"] is None


def test_critique_followup_prompt_includes_previous_output(tmp_path: Path):
    """Inspect the second-leg prompt the adapter receives: it must contain the
    first-leg output verbatim (the model is reviewing its own answer) and end
    with the locked canonical critique prompt.
    """
    task = StructuredExtractionTask(n_instances=1, seed=42, max_attempts=1)
    instances = list(task.dataset_loader())
    bad = '{"invoice_number": "WRONG"}'
    good = _good_extraction_output(instances[0])
    adapter = _make_mock_adapter([bad, good])

    run_task_for_provider(
        task=task,
        adapter=adapter,
        n_runs=1,
        cost_tracker=CostTracker(max_usd=1.0),
        git_sha="deadbeef",
        git_dirty=False,
        repo_dir=tmp_path,
        output_dir=tmp_path,
        critique_pass=True,
    )

    assert adapter.call.call_count == 2
    # Second call is leg B; first positional arg is the prompt.
    second_call_prompt = adapter.call.call_args_list[1].args[0]
    assert bad in second_call_prompt
    assert second_call_prompt.endswith(CANONICAL_CRITIQUE_PROMPT)


def test_site_builder_pairs_critique_delta_rows():
    """End-to-end check on `_critique_delta_rows` in site/build.py: matched
    (provider, model) pairs across off and on passes get a delta row;
    models present in only one pass are excluded.
    """
    import sys

    site_dir = Path(__file__).resolve().parent.parent / "site"
    if str(site_dir) not in sys.path:
        sys.path.insert(0, str(site_dir))
    from build import _critique_delta_rows  # type: ignore[import-not-found]

    off_pass = {
        "entries": [
            {
                "provider": "anthropic",
                "model": "claude-sonnet-4-6",
                "model_class": "standard",
                "effective_tcot": 0.001,
                "effective_tcot_infinite": False,
                "success_rate": 1.0,
            },
            {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "model_class": "standard",
                "effective_tcot": 0.0005,
                "effective_tcot_infinite": False,
                "success_rate": 0.8,
            },
        ]
    }
    on_pass = {
        "entries": [
            {
                "provider": "anthropic",
                "model": "claude-sonnet-4-6",
                "model_class": "standard",
                "effective_tcot": 0.0015,  # 50% more
                "effective_tcot_infinite": False,
                "success_rate": 1.0,  # no change
            },
            # OpenAI not in on_pass; should be excluded from delta rows.
        ]
    }

    rows = _critique_delta_rows(off_pass, on_pass)
    assert len(rows) == 1
    row = rows[0]
    assert row["provider"] == "anthropic"
    assert row["model"] == "claude-sonnet-4-6"
    assert math.isclose(row["delta_eff_pct"], 50.0, abs_tol=1e-6)
    assert math.isclose(row["delta_success_pp"], 0.0, abs_tol=1e-9)


def test_critique_delta_rows_returns_empty_when_either_missing():
    """If only off or only on exists, no deltas can be computed."""
    import sys

    site_dir = Path(__file__).resolve().parent.parent / "site"
    if str(site_dir) not in sys.path:
        sys.path.insert(0, str(site_dir))
    from build import _critique_delta_rows  # type: ignore[import-not-found]

    a_pass: dict[str, Any] = {"entries": []}
    assert _critique_delta_rows(None, a_pass) == []
    assert _critique_delta_rows(a_pass, None) == []
    assert _critique_delta_rows(None, None) == []


def test_critique_pass_field_on_result_json_persisted(tmp_path: Path):
    """The top-level critique_pass field on the result JSON must be present
    and accurately reflect the run mode so site/build.py can split the two
    tracks.
    """
    task = StructuredExtractionTask(n_instances=1, seed=42, max_attempts=1)
    instances = list(task.dataset_loader())
    outputs = [_good_extraction_output(instances[0]), _good_extraction_output(instances[0])]
    adapter = _make_mock_adapter(outputs)

    record = run_task_for_provider(
        task=task,
        adapter=adapter,
        n_runs=1,
        cost_tracker=CostTracker(max_usd=1.0),
        git_sha="deadbeef",
        git_dirty=False,
        repo_dir=tmp_path,
        output_dir=tmp_path,
        critique_pass=True,
    )
    assert "critique_pass" in record
    assert record["critique_pass"] is True


def test_methodology_version_bumped_to_0_2():
    """Sanity check that the runtime constant matches the doc bump in this
    same PR. If these drift, result JSONs will record the wrong methodology
    version and downstream consumers can't trust the track semantics.
    """
    from bellwether import __methodology_version__

    assert __methodology_version__ == "0.2"


def _assert_no_critique_on_legacy_entry():
    """Documentation-only helper: legacy result JSONs (pre-v0.2) lack the
    critique_pass field. site/build.py defaults to False per `r.get(...)`,
    keeping the v0.1.x leaderboard byte-equivalent. Covered indirectly by
    the build-time smoke test; named here for future readers.
    """
    pass
