"""Build the static results site from results/ JSON files into docs/.

GH Pages is configured to serve from main branch /docs. Re-run after each new
bench. The build is deterministic: same inputs produce byte-identical HTML.

No JS for layout; one tiny inline JS block on index.html powers the cost
calculator widget. The page degrades gracefully if JS is disabled.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import markdown
from jinja2 import Environment, FileSystemLoader

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "results"
SITE_DIR = REPO_ROOT / "site"
DOCS_DIR = REPO_ROOT / "docs"
METHODOLOGY_MD = REPO_ROOT / "METHODOLOGY.md"
GLOSSARY_MD = SITE_DIR / "glossary.md"

# Two adjacent ranks are tagged "tied within noise" when the ratio of their
# effective_TCoT values is within this fraction. Conservative; with N=3 the
# headline metric carries real noise. v0.4 will replace this heuristic with
# bootstrap CIs.
TIED_RANK_RATIO_THRESHOLD = 0.05  # 5%


def _load_results() -> list[dict[str, Any]]:
    """Load every results/*.json file. Sorted by file path for stable ordering."""
    return [json.loads(p.read_text()) for p in sorted(RESULTS_DIR.rglob("*.json"))]


def _attempt_metrics(result: dict[str, Any]) -> dict[str, Any]:
    """Walk instances/runs/attempts in one result; aggregate attempt-level metrics.

    Returns:
        n_attempts_total: count of all attempts across every (instance, run)
        n_first_attempt_pass: count of trials that passed validation on attempt 1
        n_trials: number of (instance, run) pairs benched
        failure_mode_counts: per-mode counts across ALL attempts
    """
    n_attempts_total = 0
    n_first_attempt_pass = 0
    n_trials = 0
    failure_mode_counts: dict[str, int] = {}
    for instance in result.get("instances", []):
        for run in instance.get("runs", []):
            attempts = run.get("attempts", [])
            if not attempts:
                continue
            n_trials += 1
            n_attempts_total += len(attempts)
            if attempts[0]["validation"]["passed"]:
                n_first_attempt_pass += 1
            for att in attempts:
                for mode in att.get("validation", {}).get("failure_modes", []):
                    failure_mode_counts[mode] = failure_mode_counts.get(mode, 0) + 1
    return {
        "n_attempts_total": n_attempts_total,
        "n_first_attempt_pass": n_first_attempt_pass,
        "n_trials": n_trials,
        "first_attempt_pass_rate": (n_first_attempt_pass / n_trials) if n_trials else 0.0,
        "failure_mode_counts": failure_mode_counts,
    }


def _entry_from_result(r: dict[str, Any]) -> dict[str, Any]:
    """Flatten a result JSON into a render-ready dict for the leaderboard."""
    agg = r["aggregate"]
    prov = r["provider"]
    attempt_m = _attempt_metrics(r)
    return {
        "provider": prov["id"],
        "model": prov["model_id"],
        "success_rate": agg["success_rate"],
        "effective_tcot": agg["effective_tcot"],
        "effective_tcot_infinite": agg["effective_tcot_infinite"],
        "p50": agg["mean_latency_p50"],
        "p95": agg["mean_latency_p95"],
        "std_tcot_success": agg.get("std_tcot_success", 0.0),
        "std_latency": agg.get("std_latency", 0.0),
        "git_dirty": r["git_dirty"],
        "git_sha": r["git_sha"],
        "n_trials": attempt_m["n_trials"],
        "n_successes": agg["n_successes"],
        "n_attempts_total": attempt_m["n_attempts_total"],
        "n_first_attempt_pass": attempt_m["n_first_attempt_pass"],
        "first_attempt_pass_rate": attempt_m["first_attempt_pass_rate"],
        "failure_mode_counts": attempt_m["failure_mode_counts"],
    }


def _annotate_pass(entries: list[dict[str, Any]]) -> None:
    """Sort + rank entries within a pass, compute cost-bar widths and tied flags."""
    entries.sort(
        key=lambda e: (1 if e["effective_tcot_infinite"] else 0, e["effective_tcot"] or 0)
    )
    for i, entry in enumerate(entries, 1):
        entry["rank"] = i

    # Inline cost-bar widths normalize within this pass.
    costs = [e["effective_tcot"] for e in entries if not e["effective_tcot_infinite"]]
    max_cost = max(costs) if costs else 1.0
    for e in entries:
        if e["effective_tcot_infinite"] or max_cost == 0:
            e["cost_bar_pct"] = 100
        else:
            e["cost_bar_pct"] = max(2, int((e["effective_tcot"] / max_cost) * 100))

    # Tied-rank flag: this entry is "tied within noise" with the rank above
    # if their effective_tcot values are within TIED_RANK_RATIO_THRESHOLD.
    for i, e in enumerate(entries):
        if i == 0 or e["effective_tcot_infinite"]:
            e["tied_with_above"] = False
            continue
        prev = entries[i - 1]
        if prev["effective_tcot_infinite"] or prev["effective_tcot"] in (None, 0):
            e["tied_with_above"] = False
            continue
        ratio = abs(e["effective_tcot"] - prev["effective_tcot"]) / prev["effective_tcot"]
        e["tied_with_above"] = ratio <= TIED_RANK_RATIO_THRESHOLD


def _passes_by_task(results: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group results by (task_name, pass identified by started_at), ranked + annotated."""
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for r in results:
        if r.get("aggregate") is None:
            continue
        grouped[r["task"]["name"]][r["started_at"]].append(_entry_from_result(r))

    output: dict[str, list[dict[str, Any]]] = {}
    for task_name, passes in grouped.items():
        sorted_passes = []
        for started_at in sorted(passes.keys(), reverse=True):
            entries = passes[started_at]
            _annotate_pass(entries)
            sorted_passes.append(
                {
                    "started_at": started_at,
                    "git_sha_short": entries[0]["git_sha"][:7] if entries[0]["git_sha"] else "?",
                    "any_dirty": any(e["git_dirty"] for e in entries),
                    "entries": entries,
                }
            )
        output[task_name] = sorted_passes
    return output


def _reproducibility(passes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-provider deltas across the two most recent passes (if 2+ exist)."""
    if len(passes) < 2:
        return []
    latest = passes[0]
    previous = passes[1]
    by_latest = {f'{e["provider"]}/{e["model"]}': e for e in latest["entries"]}
    by_prev = {f'{e["provider"]}/{e["model"]}': e for e in previous["entries"]}

    output = []
    for provider_model in sorted(by_latest.keys()):
        if provider_model not in by_prev:
            continue
        a = by_latest[provider_model]
        b = by_prev[provider_model]
        if a["effective_tcot_infinite"] or b["effective_tcot_infinite"]:
            delta_pct = None
        elif b["effective_tcot"] in (None, 0):
            delta_pct = None
        else:
            delta_pct = (a["effective_tcot"] - b["effective_tcot"]) / b["effective_tcot"] * 100
        output.append(
            {
                "provider_model": provider_model,
                "provider": a["provider"],
                "latest_eff": a["effective_tcot"],
                "previous_eff": b["effective_tcot"],
                "delta_eff_pct": delta_pct,
                "delta_success_pp": (a["success_rate"] - b["success_rate"]) * 100,
                "latest_dirty": a["git_dirty"],
                "previous_dirty": b["git_dirty"],
            }
        )
    return output


def _latest_clean_pass(passes: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the most recent pass whose entries are all clean-tree, else None."""
    for p in passes:
        if not p["any_dirty"]:
            return p
    return None


def _aggregate_failure_modes_per_provider(
    passes: list[dict[str, Any]],
) -> dict[str, dict[str, int]]:
    """For the per-task page: failure-mode totals per (provider/model) across ALL passes."""
    out: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for p in passes:
        for entry in p["entries"]:
            key = f'{entry["provider"]}/{entry["model"]}'
            for mode, count in entry["failure_mode_counts"].items():
                out[key][mode] += count
    return {k: dict(v) for k, v in out.items()}


def _render_md(path: Path, with_toc: bool = False) -> tuple[str, str]:
    """Convert a Markdown file to (body_html, toc_html). toc_html is empty when disabled."""
    text = path.read_text()
    extensions = ["tables", "fenced_code"]
    if with_toc:
        extensions.append("toc")
    md = markdown.Markdown(extensions=extensions)
    body = md.convert(text)
    toc = md.toc if with_toc else ""  # type: ignore[attr-defined]
    return body, toc


def main() -> None:
    DOCS_DIR.mkdir(exist_ok=True)
    (DOCS_DIR / "tasks").mkdir(exist_ok=True)

    results = _load_results()
    tasks = _passes_by_task(results)

    task_views: dict[str, dict[str, Any]] = {}
    for task_name, passes in tasks.items():
        task_views[task_name] = {
            "passes": passes,
            "latest_clean": _latest_clean_pass(passes),
            "reproducibility": _reproducibility(passes),
            "failure_modes_aggregated": _aggregate_failure_modes_per_provider(passes),
            "n_passes": len(passes),
        }

    latest_bench = max((r["completed_at"] for r in results), default="never")
    bellwether_version = results[0]["bellwether_version"] if results else "0.1.0"
    methodology_version = results[0]["methodology_version"] if results else "0.1"

    methodology_body, methodology_toc = _render_md(METHODOLOGY_MD, with_toc=True)
    glossary_body = ""
    if GLOSSARY_MD.exists():
        glossary_body, _ = _render_md(GLOSSARY_MD, with_toc=False)

    env = Environment(loader=FileSystemLoader(SITE_DIR), autoescape=True)

    index_html = env.get_template("index.html.j2").render(
        tasks=task_views,
        methodology_version=methodology_version,
        bellwether_version=bellwether_version,
        latest_bench_iso=latest_bench,
        n_total_results=len(results),
    )
    (DOCS_DIR / "index.html").write_text(index_html)

    methodology_html = env.get_template("methodology.html.j2").render(
        methodology_html_body=methodology_body,
        methodology_toc_html=methodology_toc,
        methodology_version=methodology_version,
    )
    (DOCS_DIR / "methodology.html").write_text(methodology_html)

    if glossary_body:
        glossary_html = env.get_template("glossary.html.j2").render(
            glossary_html_body=glossary_body,
        )
        (DOCS_DIR / "glossary.html").write_text(glossary_html)

    # Per-task drill-down pages.
    for task_name, view in task_views.items():
        task_page_html = env.get_template("task_detail.html.j2").render(
            task_name=task_name,
            view=view,
            methodology_version=methodology_version,
            bellwether_version=bellwether_version,
        )
        (DOCS_DIR / "tasks" / f"{task_name}.html").write_text(task_page_html)

    (DOCS_DIR / ".nojekyll").write_text("")

    print(f"Wrote {DOCS_DIR / 'index.html'}")
    print(f"Wrote {DOCS_DIR / 'methodology.html'}")
    if glossary_body:
        print(f"Wrote {DOCS_DIR / 'glossary.html'}")
    for task_name in task_views:
        print(f"Wrote {DOCS_DIR / 'tasks' / f'{task_name}.html'}")
    print(f"Tasks rendered: {list(task_views.keys())}")
    print(f"Total result files: {len(results)}")


if __name__ == "__main__":
    main()
