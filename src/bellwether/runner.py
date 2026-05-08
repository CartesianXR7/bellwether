"""Runner: orchestrates a benchmark run for one (task, provider) pair.

Per METHODOLOGY s2/s3/s7/s9:
- Iterates task instances; per instance, runs N times for stochasticity reporting (s7).
- Per run, retries up to max_attempts with schema-only failure_reason in retry prompt (s3).
- Computes cost from pricing.lookup at runner time (adapters return token counts).
- Records per-attempt JSON per s9 schema, including git_dirty for the dirty-tree check.
- Honors CostTracker guardrail; halts gracefully on trip and records 'skipped' in JSON.
"""

from __future__ import annotations

import json
import logging
import math
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bellwether import __methodology_version__, __version__
from bellwether.guardrail import CostTracker
from bellwether.pricing import PRICING_VERSION, Pricing, lookup
from bellwether.protocols import Example, ProviderAdapter, ProviderResponse, Task, ValidationResult
from bellwether.taxonomy import FailureMode, derive_runtime_failure_modes
from bellwether.tcot import AggregateMetrics, Attempt, InstanceResult, aggregate

logger = logging.getLogger(__name__)

# Untracked files under these path prefixes do NOT count as a dirty tree.
# These are build artifacts the runner itself produces; if they triggered the
# dirty-tree gate, every back-to-back run would refuse without --allow-dirty.
DIRTY_IGNORE_UNTRACKED_PREFIXES: tuple[str, ...] = ("results/", "docs/")


def is_dirty_status(status_porcelain: str) -> bool:
    """Parse `git status --porcelain` output into a boolean dirty flag.

    Untracked paths under DIRTY_IGNORE_UNTRACKED_PREFIXES are ignored.
    Everything else (modified, staged, deleted, renamed, other untracked)
    counts as dirty.
    """
    for line in status_porcelain.splitlines():
        if not line.strip():
            continue
        marker = line[:2]
        path = line[3:] if len(line) > 3 else ""
        if path.startswith('"') and path.endswith('"'):
            path = path[1:-1]
        if marker == "??" and any(path.startswith(p) for p in DIRTY_IGNORE_UNTRACKED_PREFIXES):
            continue
        return True
    return False


def get_git_state(repo_dir: Path) -> tuple[str, bool]:
    """Return (git_sha, git_dirty). Falls back to ('UNKNOWN', True) if git fails.

    UNKNOWN sha + dirty=True means the runner will refuse to write headline
    aggregates from this state unless --allow-dirty is passed. This is the
    intended behavior for repos with no commits yet.
    """
    try:
        sha = (
            subprocess.check_output(
                ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ("UNKNOWN", True)

    try:
        status = subprocess.check_output(
            ["git", "-C", str(repo_dir), "status", "--porcelain"],
            stderr=subprocess.DEVNULL,
        ).decode()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return (sha, True)

    return (sha, is_dirty_status(status))


def run_task_for_provider(
    *,
    task: Task,
    adapter: ProviderAdapter,
    n_runs: int,
    cost_tracker: CostTracker,
    git_sha: str,
    git_dirty: bool,
    repo_dir: Path,
    output_dir: Path,
    timestamp_iso: str | None = None,
    call_delay_seconds: float = 0.0,
) -> dict[str, Any]:
    """Run one task across all instances against one provider, N runs each.

    Returns the JSON-serializable result dict that was also written to
    output_dir. Shape matches METHODOLOGY s9.
    """
    pricing = lookup(adapter.provider_id, adapter.model_id)
    started_at = timestamp_iso or datetime.now(UTC).isoformat()

    # Per-provider rate limiter: enforces minimum interval between API call
    # starts. Shared across all instances/runs/attempts in this (task, provider).
    # Cheap defense against 429s on free-tier or low-throughput keys.
    last_request_start: list[float | None] = [None]

    def _rate_limit() -> None:
        if call_delay_seconds <= 0:
            return
        now = time.monotonic()
        if last_request_start[0] is not None:
            elapsed = now - last_request_start[0]
            if elapsed < call_delay_seconds:
                time.sleep(call_delay_seconds - elapsed)
        last_request_start[0] = time.monotonic()

    instances_loaded = list(task.dataset_loader())

    instance_records: list[dict[str, Any]] = []
    instance_results_for_aggregate: list[InstanceResult] = []
    stopped_early: str | None = None

    logger.info(
        f"=== {adapter.provider_id}/{adapter.model_id} / {task.name} "
        f"({len(instances_loaded)} instances x {n_runs} runs, max_attempts={task.max_attempts}) ==="
    )

    for example in instances_loaded:
        if cost_tracker.tripped:
            stopped_early = (
                f"cost guardrail tripped at ${cost_tracker.spent_usd:.4f} "
                f">= ${cost_tracker.max_usd:.4f} cap"
            )
            logger.warning(f"STOPPING: {stopped_early}")
            break

        instance_runs: list[dict[str, Any]] = []
        for run_idx in range(n_runs):
            if cost_tracker.tripped:
                break
            run_record, maybe_result = _run_single_attempt_loop(
                task=task,
                adapter=adapter,
                example=example,
                run_idx=run_idx,
                pricing=pricing,
                cost_tracker=cost_tracker,
                rate_limit_fn=_rate_limit,
            )
            instance_runs.append(run_record)
            if maybe_result is not None:
                instance_results_for_aggregate.append(maybe_result)

        instance_records.append({"instance_id": example.instance_id, "runs": instance_runs})

    completed_at = datetime.now(UTC).isoformat()
    aggregate_metrics = (
        aggregate(instance_results_for_aggregate) if instance_results_for_aggregate else None
    )

    record: dict[str, Any] = {
        "bellwether_version": __version__,
        "methodology_version": __methodology_version__,
        "git_sha": git_sha,
        "git_dirty": git_dirty,
        "pricing_version": PRICING_VERSION,
        "provider": {
            "id": adapter.provider_id,
            "model_id": adapter.model_id,
            "model_version_hint": None,
            "model_class": pricing.model_class,
        },
        "task": {
            "name": task.name,
            "dataset_version": task.dataset_version,
            "max_attempts": task.max_attempts,
            "pass_threshold": task.pass_threshold,
        },
        "n_runs_per_instance": n_runs,
        "started_at": started_at,
        "completed_at": completed_at,
        "instances": instance_records,
        "aggregate": _aggregate_to_dict(aggregate_metrics) if aggregate_metrics else None,
        "cost_guardrail": {
            "max_usd": cost_tracker.max_usd,
            "spent_usd": cost_tracker.spent_usd,
            "tripped": cost_tracker.tripped,
        },
        "stopped_early": stopped_early,
    }

    out_path = _write_result(
        record, output_dir, git_sha, adapter.provider_id, task.name, adapter.model_id
    )
    logger.info(f"Wrote {out_path}")
    return record


def _run_single_attempt_loop(
    *,
    task: Task,
    adapter: ProviderAdapter,
    example: Example,
    run_idx: int,
    pricing: Pricing,
    cost_tracker: CostTracker,
    rate_limit_fn: Callable[[], None] | None = None,
) -> tuple[dict[str, Any], InstanceResult | None]:
    """Run one (instance, run) up to max_attempts with retries per s3.

    Returns (run_json_record, instance_result_or_none). When the cost tracker
    trips before any attempt, instance_result is None (skipped) and the JSON
    record carries skipped_reason so the leaderboard is honest about gaps.
    """
    base_prompt = task.canonical_prompt_template.format(**example.prompt_inputs)
    conversation_messages: list[dict[str, str]] = []
    attempt_records: list[dict[str, Any]] = []
    attempts_for_metrics: list[Attempt] = []
    final_validation: ValidationResult | None = None
    final_response: ProviderResponse | None = None

    for attempt_idx in range(task.max_attempts):
        if cost_tracker.tripped:
            break

        if rate_limit_fn is not None:
            rate_limit_fn()

        prompt = _build_retry_prompt(base_prompt, conversation_messages)
        response = adapter.call(prompt, max_tokens=2048)
        cost_usd = _compute_cost(response, pricing)
        cost_tracker.charge(cost_usd)

        if response.error:
            validation = ValidationResult(
                passed=False,
                score=0.0,
                failure_reason=f"provider error: {response.error[:120]}",
                failure_modes=[FailureMode.ERROR],
            )
        else:
            try:
                validation = task.validator(response.output_text, example.ground_truth)
            except Exception as exc:
                validation = ValidationResult(
                    passed=False,
                    score=0.0,
                    failure_reason=f"validator raised: {type(exc).__name__}",
                    failure_modes=[FailureMode.ERROR],
                )

        attempt_records.append(
            {
                "attempt": attempt_idx + 1,
                "prompt_chars": len(prompt),
                "output": response.output_text,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "cost_usd": cost_usd,
                "latency_seconds": response.latency_seconds,
                "finish_reason": response.finish_reason,
                "error": response.error,
                "validation": {
                    "passed": validation.passed,
                    "score": validation.score,
                    "failure_reason": validation.failure_reason,
                    "failure_modes": [m.value for m in validation.failure_modes],
                },
            }
        )
        attempts_for_metrics.append(
            Attempt(
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                cost_usd=cost_usd,
                latency_seconds=response.latency_seconds,
            )
        )

        outcome = (
            "PASS"
            if validation.passed
            else f"FAIL[{','.join(m.value for m in validation.failure_modes) or 'unknown'}]"
        )
        logger.info(
            f"  [{adapter.provider_id}/{adapter.model_id}] {task.name} {example.instance_id} "
            f"run={run_idx} attempt={attempt_idx + 1} {outcome} "
            f"({response.latency_seconds:.2f}s, ${cost_usd:.4f})"
        )

        final_validation = validation
        final_response = response

        if validation.passed:
            break

        # Retry feedback per s3: schema/format level only. The validator's
        # failure_reason is what we echo; if a validator emits content-level
        # reasons that's a validator bug, not a runner concern.
        conversation_messages.append(
            {
                "previous_output": response.output_text,
                "failure_reason": validation.failure_reason or "validation failed",
            }
        )

    if not attempts_for_metrics:
        return (
            {
                "run_idx": run_idx,
                "attempts": [],
                "succeeded": False,
                "skipped_reason": "cost_guardrail",
            },
            None,
        )

    succeeded = bool(final_validation and final_validation.passed)
    runtime_modes: list[FailureMode] = []
    if final_response is not None and not succeeded:
        runtime_modes = derive_runtime_failure_modes(
            output=final_response.output_text,
            finish_reason=final_response.finish_reason,
            timed_out=False,
            api_error=final_response.error,
        )
    validator_modes = list(final_validation.failure_modes) if final_validation else []
    combined_modes = _union_modes(validator_modes, runtime_modes)
    if not succeeded and not combined_modes:
        combined_modes = [FailureMode.CONFABULATION]

    instance_result = InstanceResult(
        instance_id=f"{example.instance_id}#run{run_idx}",
        attempts=attempts_for_metrics,
        succeeded=succeeded,
        failure_modes=[] if succeeded else combined_modes,
    )

    run_record = {
        "run_idx": run_idx,
        "attempts": attempt_records,
        "succeeded": succeeded,
        "tcot_usd": instance_result.tcot,
        "failure_modes": [] if succeeded else [m.value for m in combined_modes],
    }
    return run_record, instance_result


def _build_retry_prompt(base_prompt: str, history: list[dict[str, str]]) -> str:
    if not history:
        return base_prompt
    parts = [base_prompt]
    for h in history:
        parts.append(
            f"\n\nPrevious response:\n{h['previous_output']}\n\n"
            f"Your previous response failed validation: {h['failure_reason']}. "
            f"Please correct and try again, outputting only the JSON object."
        )
    return "".join(parts)


def _compute_cost(response: ProviderResponse, pricing: Pricing) -> float:
    # Defensive: if an adapter ever returns None for either count (e.g. a
    # provider SDK returning a usage object with missing fields), coerce to 0
    # so arithmetic never raises mid-bench.
    in_tok = response.input_tokens or 0
    out_tok = response.output_tokens or 0
    return (
        in_tok / 1_000_000 * pricing.input_per_million_usd
        + out_tok / 1_000_000 * pricing.output_per_million_usd
    )


def _union_modes(*lists: list[FailureMode]) -> list[FailureMode]:
    seen: list[FailureMode] = []
    for lst in lists:
        for m in lst:
            if m not in seen:
                seen.append(m)
    return seen


def _aggregate_to_dict(m: AggregateMetrics) -> dict[str, Any]:
    return {
        "n_instances": m.n_instances,
        "n_successes": m.n_successes,
        "success_rate": m.success_rate,
        "mean_tcot_success": m.mean_tcot_success,
        "mean_tcot_failure": m.mean_tcot_failure,
        # JSON cannot represent inf; coerce to null with a flag.
        "effective_tcot": (None if math.isinf(m.effective_tcot) else m.effective_tcot),
        "effective_tcot_infinite": math.isinf(m.effective_tcot),
        "mean_latency_p50": m.mean_latency_p50,
        "mean_latency_p95": m.mean_latency_p95,
        "std_tcot_success": m.std_tcot_success,
        "std_latency": m.std_latency,
    }


def _write_result(
    record: dict[str, Any],
    output_dir: Path,
    git_sha: str,
    provider_id: str,
    task_name: str,
    model_id: str = "",
) -> Path:
    """Write to output_dir/<date>/<provider>/<task>__<model>__<sha7>.json.

    model_id is sanitized (slashes and colons -> underscores) so OpenRouter-
    style ids like 'meta-llama/llama-4-scout' don't break the filesystem.
    Multiple distinct models can share provider_id (e.g. all 8 OpenRouter
    models), so the model_id segment is required to keep filenames unique.
    """
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    sha7 = (git_sha or "UNKNOWN")[:7]
    target_dir = output_dir / date_str / provider_id
    target_dir.mkdir(parents=True, exist_ok=True)
    sanitized_model = (model_id or "model").replace("/", "_").replace(":", "_")
    base = f"{task_name}__{sanitized_model}__{sha7}"
    target_path = target_dir / f"{base}.json"
    if target_path.exists():
        ts = datetime.now(UTC).strftime("%H%M%S")
        target_path = target_dir / f"{base}__{ts}.json"
    target_path.write_text(json.dumps(record, indent=2, default=str))
    return target_path
