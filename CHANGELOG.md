# Changelog

All notable changes are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); methodology
versioning per METHODOLOGY.md s11.

## [v0.3.0] - 2026-05-07

Procurement-question reach: 3 tasks across 8 provider models, with statistical
rigor and a much more useful leaderboard.

### Tasks (was 1, now 3)

- **function_call_routing**: synthetic tool-selection task. Model sees a
  6-tool registry and a user query; outputs JSON with tool name + arguments.
  Score 1.0 (correct tool + args), 0.5 (correct tool, wrong args -> PARTIAL),
  0.0 (wrong tool -> CONFABULATION). Deterministic generator avoids the
  BFCL dataset dependency for v0.x; real-dataset upgrade is v1.
- **synthetic_rag**: read a 4-sentence synthetic passage about a company,
  answer one fact-retrieval question. Case-insensitive exact match with
  light normalization (whitespace, surrounding quotes, trailing period).
  Avoids FinanceBench / NQ-open / HotpotQA license complications;
  real-dataset upgrade is v1.

### Providers (was 3, now 8)

PRICING_TABLE expanded from 3 to 8 entries. All values verified against
LiteLLM pricing catalog and provider docs (output cost >= input cost
sanity check enforced in tests):

- anthropic/claude-haiku-4-5 ($1 / $5 per M)
- anthropic/claude-opus-4-7 ($5 / $25 per M)
- openai/gpt-4o-mini ($0.15 / $0.60 per M)
- google/gemini-2.5-flash ($0.30 / $2.50 per M, thinking model)
- google/gemini-2.5-pro ($1.25 / $10 per M)

CLI registry now keys both provider-name aliases (anthropic/openai/google
-> their default model) and direct model_ids. `--provider all` iterates
all 8 distinct (provider, model) entries.

### Methodology rigor (s7 spec gap closed)

- **mean +/- std reporting** on `effective_TCoT` per s7. AggregateMetrics
  gains `std_tcot_success` and `std_latency`; population stddev across
  per-trial costs / per-attempt latencies; reported as 0.0 when fewer
  than 2 observations (avoids NaN).
- **Tied-rank marker**: adjacent ranks within 5% on `effective_TCoT` are
  visually marked tied within bench noise. v0.4 will replace the heuristic
  with bootstrap confidence intervals.

### Site UI

- **Per-task drill-down pages** at `docs/tasks/<task_name>.html` with full
  reproducibility table, all-pass aggregated failure-mode totals, and full
  per-pass breakdowns. Linked from each task header on the index.
- **Latest-clean-pass headline** per task on the index, per s9 honest
  reporting rule (dirty-tree passes are non-headline).
- **Inline cost calculator widget**: enter "tasks per month" and JS computes
  per-provider monthly cost from the pass's `effective_TCoT`.
- **Glossary page** with plain-English definitions of every metric, every
  failure mode, every status flag, and the methodology concepts that
  appear on the leaderboard.
- Inline cost-bar widths normalize per-pass; provider-color swatches
  consistent across leaderboard, drill-down, and reproducibility tables.

### Bug fixes

- providers/google.py coerces None token counts to 0. Gemini 2.5 Pro and
  Flash thinking models can return `None` for `candidates_token_count`
  when the entire output budget is consumed by internal thinking and no
  visible text is produced; this previously crashed the runner mid-bench
  with TypeError in the cost computation.
- runner._compute_cost defensive coercion: any None token count from any
  adapter coerces to 0.

### Documentation

- `ARCHITECTURE.md`: layered structure, module map, key design decisions,
  rationale for synchronous runner / no async (yet) and synthetic-task
  approach for v0.x.
- `ROADMAP.md`: shipped (v0.1, v0.3), next (v0.4: async runner + BYO config
  + plugin loader + bootstrap CIs), later (v0.5), v1 (real datasets,
  open-weights, code-gen with sandboxing).
- `CODE_OF_CONDUCT.md`: Contributor Covenant 2.1.
- `CITATION.cff` + BibTeX block in README. GitHub renders a "Cite this
  repository" button from the .cff file.

### Tests

144 passing (was 120). Includes ground-truth-leak checks on the two new
task validators per METHODOLOGY s3, and a sanity test that every pricing
row has output_cost >= input_cost.

---

## [v0.1.0] - 2026-05-06

Initial release. Methodology v0.1.

### Methodology

- `effective_TCoT` formula corrected to include failed-attempt waste
  (METHODOLOGY s2.3). The naive `mean_TCoT_success / success_rate`
  shorthand systematically undercounts when failures are costlier than
  successes; the corrected formula `mean_TCoT_success +
  mean_TCoT_failure * (1 - success_rate) / success_rate` is the
  headline metric.
- Schema-only retry feedback enforced (s3): `failure_reason` may not
  echo expected values, name missing entities (other than schema
  fields), report F1 deltas, or quote ground truth in any form.
- Temperature-zero caveat (s7): T=0 minimizes stochasticity but does
  not guarantee determinism; mean +/- std reporting acknowledges this.
- Dirty-tree handling (s9): runner refuses to write headline aggregates
  from a dirty tree without `--allow-dirty`; dirty results are flagged
  and excluded from leaderboard headlines.
- Honest reporting checklist (s12): all providers shown for all tasks,
  success rate < 1.0 surfaced, dirty results flagged, ranks within 1
  std visually marked tied.

### Package

- Cost meter and TCoT formulas in `bellwether.tcot`.
- 8-mode failure taxonomy in `bellwether.taxonomy` with conservative
  classifiers (refusal regex bank, truncation by finish_reason and
  mid-word cutoff).
- Pricing table in `bellwether.pricing` with one verified entry per
  provider:
  - anthropic/claude-sonnet-4-6: $3 / $15 per M (verified against docs).
  - openai/gpt-4o: $2.50 / $10 per M (verified against LiteLLM catalog;
    OpenAI's pricing page is JS-only and not scrapeable).
  - google/gemini-2.5-flash-lite: $0.10 / $0.40 per M (verified against docs).
- Hard cost guardrail in `bellwether.guardrail` (`CostTracker`,
  `CostExceeded`); per-(task, provider) state, post-charge tripping,
  bounded overshoot.

### Provider adapters

- AnthropicAdapter: Messages API.
- OpenAIAdapter: Chat Completions API.
- GoogleAdapter: google-genai SDK with fresh-client-per-call workaround
  for the tenacity-retry httpx-close bug in google-genai 1.75.
- All three normalize `finish_reason` to a 4-word vocabulary
  (`stop`, `length`, `content_filter`, `tool_use`).

### Tasks

- `structured_extraction`: synthetic invoice generator (deterministic,
  license-free). Validator parses JSON output and exact-matches each
  required field. Validator is ground-truth-leak-free per s3.

### Runner

- Per-instance N-runs loop with retry (max_attempts=3 by default).
- Schema-only retry feedback in retry prompts.
- Per-attempt JSON serialization to `results/<date>/<provider>/<task>__<sha7>.json`
  matching METHODOLOGY s9.
- Dirty-tree gate ignores untracked files under `results/` and `docs/`
  (build artifacts the runner itself produces).
- Per-(task, provider) rate limiter (`--call-delay-ms`, default 200ms).
- Cost guardrail honored gracefully; instances skipped post-trip are
  recorded with `skipped_reason` rather than silently dropped.

### CLI

- `bellwether list providers` / `list tasks`.
- `bellwether run` with `--task`, `--provider`, `--n`, `--instances`,
  `--max-cost`, `--seed`, `--output`, `--allow-dirty`, `--call-delay-ms`.
- `bellwether report PATH` re-renders leaderboard from existing results.
- Top-level `--quiet`/`-q` to suppress per-attempt logs.
- SDK loggers (httpx, anthropic, openai, google-genai) pinned to
  WARNING unconditionally so the leaderboard signal is not buried in
  HTTP-request noise.
- Grouped leaderboard output: per-pass blocks with timestamp, git_sha,
  dirty flag.

### Static site

- Live at https://cartesianxr7.github.io/bellwether
- Per-pass leaderboard with failure-mode breakdown pills, attempt
  counters with first-attempt-pass rate, inline cost bars.
- Per-task reproducibility delta table (latest pass vs previous,
  color-coded for regression/improvement/within-noise).
- Methodology page with sticky TOC sidebar.
- Light/dark color scheme via `prefers-color-scheme`. Mobile responsive.
- Pure Python + Jinja2 build; no Node toolchain.

### Tests, CI

- 120 tests passing across tcot, taxonomy, pricing, guardrail, runner
  (dirty-detection helper), structured-extraction validator (incl.
  ground-truth-leak check), and adapter mocks for all three providers.
- GitHub Actions workflow runs pytest + ruff lint on push/PR, matrix
  Python 3.11 / 3.12 / 3.13.

### Documentation

- METHODOLOGY.md: locked v0.1 draft.
- README.md with badges, intro, install, run examples.
- CONTRIBUTING.md with task/provider authoring guides and methodology
  versioning rules.
- Issue templates: bug, methodology, new-task-or-provider.
