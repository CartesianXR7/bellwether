"""bellwether CLI.

Subcommands per HANDOFF s9 (subset shipped in v0.1):
    bellwether list providers
    bellwether list tasks
    bellwether run [--task NAME|all] [--provider NAME|all] [--n N]
                   [--instances N] [--max-cost USD] [--seed N]
                   [--output DIR] [--allow-dirty] [--call-delay-ms MS]
    bellwether report [PATH]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bellwether import __methodology_version__, __version__
from bellwether.guardrail import CostTracker
from bellwether.providers.anthropic import AnthropicAdapter
from bellwether.providers.google import GoogleAdapter
from bellwether.providers.openai import OpenAIAdapter
from bellwether.runner import get_git_state, run_task_for_provider
from bellwether.tasks.function_call_routing import FunctionCallRoutingTask
from bellwether.tasks.structured_extraction import StructuredExtractionTask
from bellwether.tasks.synthetic_rag import SyntheticRagTask

# Each entry: alias -> (adapter_class, provider_id, model_id, adapter_kwargs).
# The provider-name aliases ('anthropic', 'openai', 'google', 'xai',
# 'perplexity', 'openrouter') resolve to a default model; specific model_ids
# resolve to that exact model. This lets `--provider all` iterate all distinct
# (provider, model) entries while `--provider anthropic` keeps the ergonomics
# of "the default Anthropic". adapter_kwargs are extra constructor args (empty
# for native SDKs; populated for OpenAI-compatible HTTPS endpoints reusing
# OpenAIAdapter with a different base_url + key env var).

# OpenAI-compatible HTTPS endpoints (xAI Grok, Perplexity Sonar, OpenRouter)
# share the OpenAIAdapter and only differ in base_url + the env var holding
# the API key.
_OR_KW = {"base_url": "https://openrouter.ai/api/v1", "api_key_env_var": "OPENROUTER_API_KEY"}
_XAI_KW = {"base_url": "https://api.x.ai/v1", "api_key_env_var": "XAI_API_KEY"}
_PPLX_KW = {"base_url": "https://api.perplexity.ai", "api_key_env_var": "PERPLEXITY_API_KEY"}

_PROVIDER_REGISTRY: dict[str, tuple[type, str, str, dict[str, Any]]] = {
    # Anthropic
    "anthropic": (AnthropicAdapter, "anthropic", "claude-sonnet-4-6", {}),
    "claude-sonnet-4-6": (AnthropicAdapter, "anthropic", "claude-sonnet-4-6", {}),
    "claude-haiku-4-5": (AnthropicAdapter, "anthropic", "claude-haiku-4-5", {}),
    "claude-opus-4-7": (AnthropicAdapter, "anthropic", "claude-opus-4-7", {}),
    # OpenAI (standard chat + o-series reasoning)
    "openai": (OpenAIAdapter, "openai", "gpt-4o", {}),
    "gpt-4o": (OpenAIAdapter, "openai", "gpt-4o", {}),
    "gpt-4o-mini": (OpenAIAdapter, "openai", "gpt-4o-mini", {}),
    "o3": (OpenAIAdapter, "openai", "o3", {}),
    "o3-mini": (OpenAIAdapter, "openai", "o3-mini", {}),
    "o4-mini": (OpenAIAdapter, "openai", "o4-mini", {}),
    # Google
    "google": (GoogleAdapter, "google", "gemini-2.5-flash-lite", {}),
    "gemini-2.5-flash-lite": (GoogleAdapter, "google", "gemini-2.5-flash-lite", {}),
    "gemini-2.5-flash": (GoogleAdapter, "google", "gemini-2.5-flash", {}),
    "gemini-2.5-pro": (GoogleAdapter, "google", "gemini-2.5-pro", {}),
    # xAI Grok via OpenAI-compatible api.x.ai
    "xai": (OpenAIAdapter, "xai", "grok-4", _XAI_KW),
    "grok-4": (OpenAIAdapter, "xai", "grok-4", _XAI_KW),
    "grok-4-fast": (OpenAIAdapter, "xai", "grok-4-fast", _XAI_KW),
    "grok-3": (OpenAIAdapter, "xai", "grok-3", _XAI_KW),
    "grok-3-mini": (OpenAIAdapter, "xai", "grok-3-mini", _XAI_KW),
    # Perplexity Sonar via api.perplexity.ai (search + reasoning variants)
    "perplexity": (OpenAIAdapter, "perplexity", "sonar", _PPLX_KW),
    "sonar": (OpenAIAdapter, "perplexity", "sonar", _PPLX_KW),
    "sonar-pro": (OpenAIAdapter, "perplexity", "sonar-pro", _PPLX_KW),
    "sonar-reasoning": (OpenAIAdapter, "perplexity", "sonar-reasoning", _PPLX_KW),
    "sonar-reasoning-pro": (OpenAIAdapter, "perplexity", "sonar-reasoning-pro", _PPLX_KW),
    # OpenRouter (open-weights + commercial via openrouter.ai/api/v1)
    "openrouter": (
        OpenAIAdapter,
        "openrouter",
        "meta-llama/llama-3.3-70b-instruct",
        _OR_KW,
    ),
    "meta-llama/llama-4-maverick": (
        OpenAIAdapter,
        "openrouter",
        "meta-llama/llama-4-maverick",
        _OR_KW,
    ),
    "meta-llama/llama-4-scout": (
        OpenAIAdapter,
        "openrouter",
        "meta-llama/llama-4-scout",
        _OR_KW,
    ),
    "meta-llama/llama-3.3-70b-instruct": (
        OpenAIAdapter,
        "openrouter",
        "meta-llama/llama-3.3-70b-instruct",
        _OR_KW,
    ),
    "deepseek/deepseek-chat": (
        OpenAIAdapter,
        "openrouter",
        "deepseek/deepseek-chat",
        _OR_KW,
    ),
    "deepseek/deepseek-r1": (
        OpenAIAdapter,
        "openrouter",
        "deepseek/deepseek-r1",
        _OR_KW,
    ),
    "mistralai/mistral-large": (
        OpenAIAdapter,
        "openrouter",
        "mistralai/mistral-large",
        _OR_KW,
    ),
    "cohere/command-r-plus": (
        OpenAIAdapter,
        "openrouter",
        "cohere/command-r-plus",
        _OR_KW,
    ),
    "qwen/qwen-3-235b-a22b": (
        OpenAIAdapter,
        "openrouter",
        "qwen/qwen-3-235b-a22b",
        _OR_KW,
    ),
}

# Provider-name aliases that should NOT be iterated under `--provider all`
# (they are duplicates of model-id keys). The remaining keys are the canonical
# distinct (provider, model) pairs.
_PROVIDER_ALIAS_NAMES: frozenset[str] = frozenset(
    {"anthropic", "openai", "google", "xai", "perplexity", "openrouter"}
)


def _all_distinct_models() -> list[tuple[str, tuple[type, str, str, dict[str, Any]]]]:
    """Return the registry entries that are NOT provider-name aliases."""
    return [(k, v) for k, v in _PROVIDER_REGISTRY.items() if k not in _PROVIDER_ALIAS_NAMES]


_TASK_REGISTRY: dict[str, type] = {
    "structured_extraction": StructuredExtractionTask,
    "function_call_routing": FunctionCallRoutingTask,
    "synthetic_rag": SyntheticRagTask,
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bellwether",
        description="Cost-and-failure-mode benchmark for LLM agents.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"bellwether {__version__} (methodology {__methodology_version__})",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress per-attempt log lines (run subcommand).",
    )
    sub = parser.add_subparsers(dest="command", required=False)

    list_p = sub.add_parser("list", help="List registered tasks or providers.")
    list_p.add_argument("kind", choices=["tasks", "providers"])

    report_p = sub.add_parser(
        "report", help="Re-render the leaderboard from existing results without re-running."
    )
    report_p.add_argument(
        "path",
        nargs="?",
        default="results",
        help="Results directory to walk (default: ./results).",
    )

    run_p = sub.add_parser("run", help="Run benchmark for one or all (task, provider) pairs.")
    run_p.add_argument("--task", default="all", help="Task name, or 'all'. Default: all.")
    run_p.add_argument("--provider", default="all", help="Provider name, or 'all'. Default: all.")
    run_p.add_argument(
        "--n",
        type=int,
        default=3,
        help="Runs per task instance (METHODOLOGY s7 default). Default: 3.",
    )
    run_p.add_argument(
        "--instances",
        type=int,
        default=5,
        help="Task instances per run. Default: 5.",
    )
    run_p.add_argument(
        "--max-cost",
        type=float,
        default=10.0,
        help="Hard cap on total spend (USD) for the entire run. Default: 10.",
    )
    run_p.add_argument(
        "--seed", type=int, default=42, help="Seed for synthetic-task generators. Default: 42."
    )
    run_p.add_argument(
        "--output", default="results", help="Results output directory. Default: ./results"
    )
    run_p.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Allow runs from a dirty git tree (results flagged git_dirty=true).",
    )
    run_p.add_argument(
        "--call-delay-ms",
        type=int,
        default=200,
        help="Minimum ms between API calls per (task, provider) for rate limiting. Default: 200.",
    )
    run_p.add_argument(
        "--critique-pass",
        action="store_true",
        help=(
            "Enable the Critique-Pass evaluation track (METHODOLOGY s13). Each "
            "attempt wraps a single self-revision step using the locked canonical "
            "critique prompt; the post-critique output is what the validator "
            "scores. Both legs count toward TCoT."
        ),
    )

    return parser


def _load_dotenv_if_present() -> None:
    """Load .env from cwd or parents. override=True so .env wins over shell env;
    matters when a stale shell variable would otherwise mask the project's key.
    """
    try:
        from dotenv import find_dotenv, load_dotenv

        path = find_dotenv(usecwd=True)
        if path:
            load_dotenv(path, override=True)
    except ImportError:
        pass


def _cmd_list(args: argparse.Namespace) -> int:
    if args.kind == "providers":
        for name, (cls, prov_id, model_id, _kw) in _PROVIDER_REGISTRY.items():
            tag = " [alias]" if name in _PROVIDER_ALIAS_NAMES else ""
            print(f"{name}: {cls.__name__} -> {prov_id}/{model_id}{tag}")
    elif args.kind == "tasks":
        for name in _TASK_REGISTRY:
            print(name)
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    """Walk a results directory and re-print the leaderboard. No re-run, no API calls."""
    output_dir = Path(args.path)
    if not output_dir.is_dir():
        print(f"ERROR: '{output_dir}' is not a directory.", file=sys.stderr)
        return 2

    records: list[dict[str, Any]] = []
    skipped: list[tuple[Path, str]] = []
    for json_path in sorted(output_dir.rglob("*.json")):
        try:
            records.append(json.loads(json_path.read_text()))
        except (json.JSONDecodeError, OSError) as exc:
            skipped.append((json_path, f"{type(exc).__name__}: {exc}"))

    if not records:
        print(
            f"No result JSONs found under {output_dir}. Run 'bellwether run' first.",
            file=sys.stderr,
        )
        return 1

    _print_leaderboard(records)
    print(f"\nLoaded {len(records)} result file(s) from {output_dir}.", file=sys.stderr)
    if skipped:
        print(f"Skipped {len(skipped)} unreadable file(s):", file=sys.stderr)
        for path, reason in skipped:
            print(f"  {path}: {reason}", file=sys.stderr)
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    repo_dir = Path.cwd()
    git_sha, git_dirty = get_git_state(repo_dir)

    if git_dirty and not args.allow_dirty:
        print(
            "ERROR: git tree is dirty (uncommitted changes or untracked files).\n"
            "  Pass --allow-dirty to bench from this state; results will be\n"
            "  flagged git_dirty=true and excluded from headline aggregates per\n"
            f"  METHODOLOGY s9.\n"
            f"  git_sha would be: {git_sha[:7] if git_sha != 'UNKNOWN' else 'UNKNOWN'}",
            file=sys.stderr,
        )
        return 2

    if args.provider != "all" and args.provider not in _PROVIDER_REGISTRY:
        print(
            f"ERROR: unknown provider '{args.provider}'. Run 'bellwether list providers'.",
            file=sys.stderr,
        )
        return 2
    if args.task != "all" and args.task not in _TASK_REGISTRY:
        print(f"ERROR: unknown task '{args.task}'. Run 'bellwether list tasks'.", file=sys.stderr)
        return 2

    selected_providers = (
        _all_distinct_models()
        if args.provider == "all"
        else [(args.provider, _PROVIDER_REGISTRY[args.provider])]
    )
    selected_tasks = (
        list(_TASK_REGISTRY.items())
        if args.task == "all"
        else [(args.task, _TASK_REGISTRY[args.task])]
    )

    cost_tracker = CostTracker(max_usd=args.max_cost)
    timestamp = datetime.now(UTC).isoformat()
    all_records: list[dict[str, Any]] = []

    print(f"Cost guardrail: ${cost_tracker.max_usd:.2f}", file=sys.stderr)
    print(f"git_sha: {git_sha[:7]} dirty: {git_dirty}", file=sys.stderr)
    if args.critique_pass:
        print("Critique-Pass: ON (METHODOLOGY s13)", file=sys.stderr)

    for task_name, task_cls in selected_tasks:
        for prov_name, (adapter_cls, prov_id, model_id, adapter_kwargs) in selected_providers:
            if cost_tracker.tripped:
                break
            adapter = adapter_cls(provider_id=prov_id, model_id=model_id, **adapter_kwargs)
            task = task_cls(n_instances=args.instances, seed=args.seed)
            try:
                record = run_task_for_provider(
                    task=task,
                    adapter=adapter,
                    n_runs=args.n,
                    cost_tracker=cost_tracker,
                    git_sha=git_sha,
                    git_dirty=git_dirty,
                    repo_dir=repo_dir,
                    output_dir=Path(args.output),
                    timestamp_iso=timestamp,
                    call_delay_seconds=args.call_delay_ms / 1000.0,
                    critique_pass=args.critique_pass,
                )
                all_records.append(record)
            except Exception as exc:
                print(
                    f"ERROR running {task_name} on {prov_name}: {type(exc).__name__}: {exc}",
                    file=sys.stderr,
                )
        if cost_tracker.tripped:
            break

    _print_leaderboard(all_records)
    print(
        f"\nTotal spend: ${cost_tracker.spent_usd:.4f} / ${cost_tracker.max_usd:.4f}",
        file=sys.stderr,
    )
    if cost_tracker.tripped:
        print("Cost guardrail TRIPPED; some runs may be partial or skipped.", file=sys.stderr)
    return 0


def _print_leaderboard(records: list[dict[str, Any]]) -> None:
    """Print a per-task, per-pass ranked leaderboard.

    Records are grouped by (task, started_at) so each pass shows its own
    ranking. Passes within each task are ordered newest-first. Dirty-tree
    passes are flagged so the reader knows to discount them per s9.
    """
    by_task: dict[str, dict[tuple[str, bool], list[dict[str, Any]]]] = {}
    for r in records:
        if r.get("aggregate") is None:
            continue
        task = r["task"]["name"]
        # Pass-key includes critique_pass so a single report invocation that
        # loads both off and on results doesn't accidentally co-rank them.
        # critique_pass defaults to False for legacy result files (pre-v0.2).
        pass_key = (r["started_at"], bool(r.get("critique_pass", False)))
        by_task.setdefault(task, {}).setdefault(pass_key, []).append(r)

    header = (
        f"{'rank':<5} {'provider/model':<42} {'success':>9} "
        f"{'eff_TCoT':>14} {'p50/p95 (s)':>14}"
    )

    for task_name, passes in by_task.items():
        print()
        print(f"=== Leaderboard: {task_name} ===")
        for pass_key in sorted(passes.keys(), key=lambda k: (k[0], k[1]), reverse=True):
            started_at, critique_on = pass_key
            entries = passes[pass_key]
            entries.sort(
                key=lambda r: (
                    1 if r["aggregate"]["effective_tcot_infinite"] else 0,
                    r["aggregate"]["effective_tcot"] or 0,
                )
            )
            sha7 = entries[0]["git_sha"][:7] if entries[0]["git_sha"] else "UNKNOWN"
            dirty = any(e["git_dirty"] for e in entries)
            dirty_tag = " [dirty tree, s9 non-headline]" if dirty else ""
            critique_tag = " [critique-pass, s13]" if critique_on else ""
            print()
            print(
                f"-- pass {started_at[:19].replace('T', ' ')} UTC  sha {sha7}"
                f"{dirty_tag}{critique_tag}"
            )
            print(header)
            print("-" * len(header))
            for rank, r in enumerate(entries, 1):
                agg = r["aggregate"]
                prov = r["provider"]
                eff = (
                    "infinite"
                    if agg["effective_tcot_infinite"]
                    else f"${agg['effective_tcot']:.5f}"
                )
                print(
                    f"{rank:<5} "
                    f"{prov['id'] + '/' + prov['model_id']:<42} "
                    f"{agg['success_rate'] * 100:>7.1f}%  "
                    f"{eff:>14} "
                    f"{agg['mean_latency_p50']:>5.2f}/{agg['mean_latency_p95']:>5.2f}"
                )


def _silence_noisy_sdk_loggers() -> None:
    """Pin third-party SDK loggers to WARNING. The default INFO level emits one
    line per HTTP request (httpx) plus assorted notices (google-genai's AFC),
    which drowns the per-attempt PASS/FAIL signal. Silenced unconditionally;
    --quiet still applies to the runner's own logs on top of this.
    """
    for name in ("httpx", "anthropic", "openai", "google_genai", "google.genai"):
        logging.getLogger(name).setLevel(logging.WARNING)


def main(argv: list[str] | None = None) -> int:
    _load_dotenv_if_present()
    parser = _build_parser()
    args = parser.parse_args(argv)
    log_level = logging.WARNING if args.quiet else logging.INFO
    logging.basicConfig(level=log_level, format="%(message)s", stream=sys.stderr)
    _silence_noisy_sdk_loggers()
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "list":
        return _cmd_list(args)
    if args.command == "report":
        return _cmd_report(args)
    if args.command == "run":
        return _cmd_run(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
