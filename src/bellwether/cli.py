"""bellwether CLI.

Subcommands per HANDOFF s9 (subset shipped in v0.1):
    bellwether list providers
    bellwether list tasks
    bellwether run [--task NAME|all] [--provider NAME|all] [--n N]
                   [--instances N] [--max-cost USD] [--seed N]
                   [--output DIR] [--allow-dirty]
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bellwether import __methodology_version__, __version__
from bellwether.guardrail import CostTracker
from bellwether.providers.anthropic import AnthropicAdapter
from bellwether.providers.google import GoogleAdapter
from bellwether.providers.openai import OpenAIAdapter
from bellwether.runner import get_git_state, run_task_for_provider
from bellwether.tasks.structured_extraction import StructuredExtractionTask

# (provider_name, adapter_class, default_model_id)
_PROVIDER_REGISTRY: dict[str, tuple[type, str]] = {
    "anthropic": (AnthropicAdapter, "claude-sonnet-4-6"),
    "openai": (OpenAIAdapter, "gpt-4o"),
    "google": (GoogleAdapter, "gemini-2.0-flash-001"),
}

_TASK_REGISTRY: dict[str, type] = {
    "structured_extraction": StructuredExtractionTask,
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
    sub = parser.add_subparsers(dest="command", required=False)

    list_p = sub.add_parser("list", help="List registered tasks or providers.")
    list_p.add_argument("kind", choices=["tasks", "providers"])

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

    return parser


def _load_dotenv_if_present() -> None:
    try:
        from dotenv import find_dotenv, load_dotenv

        path = find_dotenv(usecwd=True)
        if path:
            load_dotenv(path)
    except ImportError:
        pass


def _cmd_list(args: argparse.Namespace) -> int:
    if args.kind == "providers":
        for name, (cls, default_model) in _PROVIDER_REGISTRY.items():
            print(f"{name}: {cls.__name__} (default model: {default_model})")
    elif args.kind == "tasks":
        for name in _TASK_REGISTRY:
            print(name)
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
        print(f"ERROR: unknown provider '{args.provider}'. Run 'bellwether list providers'.", file=sys.stderr)
        return 2
    if args.task != "all" and args.task not in _TASK_REGISTRY:
        print(f"ERROR: unknown task '{args.task}'. Run 'bellwether list tasks'.", file=sys.stderr)
        return 2

    selected_providers = (
        list(_PROVIDER_REGISTRY.items())
        if args.provider == "all"
        else [(args.provider, _PROVIDER_REGISTRY[args.provider])]
    )
    selected_tasks = (
        list(_TASK_REGISTRY.items())
        if args.task == "all"
        else [(args.task, _TASK_REGISTRY[args.task])]
    )

    cost_tracker = CostTracker(max_usd=args.max_cost)
    timestamp = datetime.now(timezone.utc).isoformat()
    all_records: list[dict[str, Any]] = []

    print(f"Cost guardrail: ${cost_tracker.max_usd:.2f}", file=sys.stderr)
    print(f"git_sha: {git_sha[:7]} dirty: {git_dirty}", file=sys.stderr)

    for task_name, task_cls in selected_tasks:
        for prov_name, (adapter_cls, default_model) in selected_providers:
            if cost_tracker.tripped:
                break
            adapter = adapter_cls(provider_id=prov_name, model_id=default_model)
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
    by_task: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        if r.get("aggregate") is None:
            continue
        by_task.setdefault(r["task"]["name"], []).append(r)

    for task_name, rs in by_task.items():
        rs.sort(
            key=lambda r: (
                1 if r["aggregate"]["effective_tcot_infinite"] else 0,
                r["aggregate"]["effective_tcot"] or 0,
            )
        )
        print()
        print(f"=== Leaderboard: {task_name} ===")
        header = (
            f"{'rank':<5} {'provider/model':<42} {'success':>9} "
            f"{'eff_TCoT':>14} {'p50/p95 (s)':>14}"
        )
        print(header)
        print("-" * len(header))
        for rank, r in enumerate(rs, 1):
            agg = r["aggregate"]
            prov = r["provider"]
            eff = "infinite" if agg["effective_tcot_infinite"] else f"${agg['effective_tcot']:.5f}"
            print(
                f"{rank:<5} "
                f"{prov['id'] + '/' + prov['model_id']:<42} "
                f"{agg['success_rate'] * 100:>7.1f}%  "
                f"{eff:>14} "
                f"{agg['mean_latency_p50']:>5.2f}/{agg['mean_latency_p95']:>5.2f}"
            )


def main(argv: list[str] | None = None) -> int:
    _load_dotenv_if_present()
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "list":
        return _cmd_list(args)
    if args.command == "run":
        return _cmd_run(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
