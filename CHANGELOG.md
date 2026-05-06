# Changelog

All notable changes are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); methodology
versioning per METHODOLOGY.md s11.

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
