"""Build the static results site from results/ JSON files into docs/.

GH Pages is configured to serve from main branch /docs. Re-run after each new
bench. The build is deterministic: same inputs produce byte-identical HTML.

No JS, no Node toolchain, no client-side rendering. Plain Jinja2 + HTML so the
page works in any browser and in screen readers.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import markdown
from jinja2 import Environment, FileSystemLoader

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "results"
SITE_DIR = REPO_ROOT / "site"
DOCS_DIR = REPO_ROOT / "docs"
METHODOLOGY_MD = REPO_ROOT / "METHODOLOGY.md"


def _load_results() -> list[dict]:
    """Load every results/*.json file. Sorted by file path for stable ordering."""
    return [json.loads(p.read_text()) for p in sorted(RESULTS_DIR.rglob("*.json"))]


def _passes_by_task(results: list[dict]) -> dict[str, list[dict]]:
    """Group results by (task_name, pass identified by started_at).

    Each pass shows providers ranked by effective_TCoT (lower is better;
    infinite goes last). Passes within each task are sorted newest-first.
    """
    grouped: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for r in results:
        if r.get("aggregate") is None:
            continue
        task_name = r["task"]["name"]
        started_at = r["started_at"]
        agg = r["aggregate"]
        prov = r["provider"]
        grouped[task_name][started_at].append(
            {
                "provider": prov["id"],
                "model": prov["model_id"],
                "success_rate": agg["success_rate"],
                "effective_tcot": agg["effective_tcot"],
                "effective_tcot_infinite": agg["effective_tcot_infinite"],
                "p50": agg["mean_latency_p50"],
                "p95": agg["mean_latency_p95"],
                "git_dirty": r["git_dirty"],
                "git_sha": r["git_sha"],
                "n_instances": agg["n_instances"],
                "n_successes": agg["n_successes"],
            }
        )

    output: dict[str, list[dict]] = {}
    for task_name, passes in grouped.items():
        sorted_passes = []
        for started_at in sorted(passes.keys(), reverse=True):
            entries = passes[started_at]
            entries.sort(
                key=lambda e: (1 if e["effective_tcot_infinite"] else 0, e["effective_tcot"] or 0)
            )
            for i, entry in enumerate(entries, 1):
                entry["rank"] = i
            sorted_passes.append(
                {
                    "started_at": started_at,
                    "git_sha_short": entries[0]["git_sha"][:7],
                    "any_dirty": any(e["git_dirty"] for e in entries),
                    "entries": entries,
                }
            )
        output[task_name] = sorted_passes
    return output


def main() -> None:
    DOCS_DIR.mkdir(exist_ok=True)

    results = _load_results()
    tasks = _passes_by_task(results)
    latest_bench = max((r["completed_at"] for r in results), default="never")
    bellwether_version = results[0]["bellwether_version"] if results else "0.1.0"
    methodology_version = results[0]["methodology_version"] if results else "0.1"

    md_text = METHODOLOGY_MD.read_text()
    md_html = markdown.markdown(md_text, extensions=["tables", "fenced_code", "toc"])

    env = Environment(loader=FileSystemLoader(SITE_DIR), autoescape=True)

    index_html = env.get_template("index.html.j2").render(
        tasks=tasks,
        methodology_version=methodology_version,
        bellwether_version=bellwether_version,
        latest_bench_iso=latest_bench,
    )
    (DOCS_DIR / "index.html").write_text(index_html)

    methodology_html = env.get_template("methodology.html.j2").render(
        methodology_html_body=md_html,
        methodology_version=methodology_version,
    )
    (DOCS_DIR / "methodology.html").write_text(methodology_html)

    # GH Pages otherwise tries to run Jekyll on the repo, which can mangle
    # the HTML and silently drop files starting with "_". Disable Jekyll.
    (DOCS_DIR / ".nojekyll").write_text("")

    print(f"Wrote {DOCS_DIR / 'index.html'}")
    print(f"Wrote {DOCS_DIR / 'methodology.html'}")
    print(f"Tasks rendered: {list(tasks.keys())}")
    print(f"Total result files: {len(results)}")


if __name__ == "__main__":
    main()
