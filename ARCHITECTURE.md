# Architecture

How bellwether is put together and why. For the *what*-it-measures see
[METHODOLOGY.md](METHODOLOGY.md); this doc covers the *how*-it-is-built
that the methodology requires.

## Layered structure

```
                +-----------------------------+
                |        CLI + site           |  user surface
                +-----------------------------+
                              |
                +-----------------------------+
                |          Runner             |  orchestration: retries,
                |  (cost guardrail, JSON IO,  |  rate limiting, JSON serialization,
                |   dirty-tree gate, retry)   |  dirty-tree refusal
                +-----------------------------+
                  |                       |
        +-------------------+    +------------------+
        |   Tasks           |    |   Providers      |  contract layers
        |   (Task Protocol) |    |   (Adapter Pcl)  |
        +-------------------+    +------------------+
                  |                       |
                +-----------------------------+
                |     Methodology core        |  pure formulas + types
                |  (TCoT, taxonomy, pricing,  |  no I/O, no external deps
                |   guardrail, protocols)     |
                +-----------------------------+
```

## Module map

```
src/bellwether/
  __init__.py             top-level exports + version constants
  protocols.py            Task and ProviderAdapter Protocols, ValidationResult,
                          Example, ProviderResponse dataclasses
  taxonomy.py             FailureMode enum + classifiers (refusal regex,
                          truncation heuristics, runtime-mode aggregator)
  tcot.py                 Attempt, InstanceResult, AggregateMetrics,
                          effective_TCoT formula, aggregate() with std
  pricing.py              Pricing dataclass, PRICING_TABLE (verified entries),
                          cost_for(), lookup()
  guardrail.py            CostTracker (hard cap, post-charge tripping)
  runner.py               run_task_for_provider, retry loop, JSON writer,
                          dirty-tree detection, per-provider rate limiter
  cli.py                  argparse + dotenv loader, list/run/report subcmds
  providers/
    anthropic.py          AnthropicAdapter (Messages API)
    openai.py             OpenAIAdapter (Chat Completions API)
    google.py             GoogleAdapter (google-genai, fresh client per call)
  tasks/
    structured_extraction.py    synthetic invoice -> JSON
    function_call_routing.py    synthetic tool selection
    synthetic_rag.py            synthetic single-fact retrieval

tests/
  test_*.py               one per module; SDK calls mocked

site/
  build.py                walks results/, renders Jinja templates -> docs/
  index.html.j2           leaderboard hub
  task_detail.html.j2     per-task drill-down
  methodology.html.j2     methodology page wrapper
  glossary.html.j2        glossary page wrapper
  glossary.md             glossary content (Markdown)

results/<date>/<provider>/<task>__<sha7>.json     committed bench output
docs/                     GH Pages output (committed; .nojekyll marker)
.github/workflows/        test.yml (CI), publish.yml (PyPI on tag)
```

## Key design decisions

### Methodology core has no I/O

`tcot.py`, `taxonomy.py`, `pricing.py`, `guardrail.py`, `protocols.py`
import only stdlib. They are pure data + formulas. This keeps the core
testable without mocks and decouples methodology bugs from integration bugs.

### Adapters and tasks satisfy Protocols structurally

No inheritance. A task is any class with the right attribute set; a provider
adapter is any class with the right call signature. This lets contributors
ship tasks/providers in a separate repo without depending on bellwether
internals beyond the Protocol surface.

### Runner owns orchestration; adapters and tasks are dumb

Adapters do one thing: turn a prompt + max_tokens into a `ProviderResponse`,
catching all SDK errors and returning them in the `error` field. Tasks do
two things: yield `Example` instances and validate output. Everything else
(retry policy, cost computation, dirty-tree gating, rate limiting, JSON
serialization, leaderboard ranking) is the runner's job. This keeps adapter
and task code small and uniform.

### Cost computed at the runner, not the adapter

Adapters report token counts; the runner multiplies by `Pricing` looked up
at run-start. This means a single adapter implementation supports any number
of pricing rows, and re-running with corrected pricing recomputes correctly
without touching adapter code.

### Hard cost guardrail

`CostTracker` is consulted before every API call. The runner halts gracefully
when tripped and records skipped instances in the JSON. Bounded overshoot:
at most one attempt's cost beyond the cap.

### Dirty-tree gate

The runner refuses to write headline aggregates from a tree with uncommitted
source changes (via `git status --porcelain` parsed by `is_dirty_status`).
Untracked files under `results/` and `docs/` are explicitly ignored because
they are build artifacts the runner itself produces. Override with
`--allow-dirty`; results are still flagged `git_dirty: true` for the
leaderboard renderer to mark non-headline.

### Schema-only retry feedback

When a trial fails and is retried, the runner appends the validator's
`failure_reason` to the next attempt's prompt. Validators are contractually
required to keep `failure_reason` at schema/format level and never echo
ground truth. Each task's test suite includes an explicit ground-truth-leak
check on this surface.

### Per-provider rate limiter inside runner

`run_task_for_provider` builds a closure over a per-(task, provider)
`last_request_start` timestamp; before every adapter call it sleeps the
remaining inter-call delay. This gives a robust min-interval enforcement
without coupling rate-limiter state to the adapter or the SDK.

### Site is built, not generated dynamically

`site/build.py` walks `results/` and renders Jinja templates into `docs/`.
Output is byte-deterministic for the same input. GH Pages serves `docs/`.
No JS for layout; one tiny inline JS block on the index drives the cost
calculator widget.

## Why no async runner (yet)

Sequential calls are simpler to reason about (one consistent rate-limit
state, one consistent cost-tracker state, deterministic per-attempt
ordering in the JSON output). Async would cut wall-clock by parallelizing
across providers within a task; planned for v0.4.

## Why synthetic tasks for v0.x

Real datasets (BFCL, FinanceBench, GAIA, GovReport) carry license,
distribution, and HF auth complications that would land badly in a v0
public release. The synthetic generators are deterministic, license-free,
and exercise the same procurement-relevant signals. v1 swaps in the real
datasets alongside the proper licensing review and the plugin loader so
contributors can ship dataset adapters in their own repos.
