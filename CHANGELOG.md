# Changelog

All notable changes are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); methodology
versioning per METHODOLOGY.md s11.

## [Unreleased]

Methodology v0.1.1 to v0.2 MINOR bump introducing the **Critique-Pass
evaluation track** as an additive dimension. The critique-off track is
byte-identical to v0.1.x semantics, so existing v0.4 results remain
comparable without re-run.

### Methodology (v0.1.1 to v0.2, MINOR bump)

- **New section 13: Critique-Pass evaluation track.** Optional dimension
  toggled by `--critique-pass`. Each attempt is wrapped with a single
  self-revision step using a locked canonical critique prompt; output
  of the critique pass is what reaches the validator. TCoT counts both
  legs per s2.1, so the critique pass is honestly billed.
- **Locked canonical critique prompt** (s13.2). Three deliberate
  choices: explicit "repeat exactly" path frames no-change as a valid
  first-class outcome to reduce sycophancy pressure; "no commentary"
  preserves the existing parser contract from the v0.1 tasks; zero
  rubric, zero validator hints, zero per-provider tuning per s6
  portability. Prompt locks once shipped.
- **Single-shot only.** Iterative-until-stable is excluded from v0.2
  because iteration count varies per model, which destroys
  cross-provider comparability (s13.1).
- **Twin-leaderboard reporting** (s13.3). Each task page renders
  critique-off (v0.1.x baseline) and critique-on side by side, plus a
  `critique_delta` column for `effective_TCoT` and `success_rate`.
  Negative success deltas are honestly reported (a model that degrades
  correct answers under critique IS the procurement signal).
- **Naming note** (s13.5). Track is intentionally not a reimplementation
  of Self-Refine (Madaan et al. 2023) or related capability-research
  protocols; cited as related work, designed for procurement
  comparability not capability maximization.
- **s10 update.** Real-world document OCR explicitly added to the
  "what this benchmark does NOT measure" list, deferred to v1. The
  synthetic-render shortcut was considered and rejected: a clean
  methodology demo on synthetic PNGs does not answer the procurement
  question buyers actually have. The v1 `document_extraction_ocr`
  task will use a redistribution-compatible open corpus and ship
  alongside image-input pricing in `pricing.py`.

### Roadmap

- v0.5 "Next" gains Critique-Pass as the headline methodology item.
- v1 gains `document_extraction_ocr` with image-input pricing, a
  `modality` field on the Task protocol, and attempt-and-classify
  vision capability detection (no hardcoded `supports_vision`).

### Not yet implemented in this version

This is a methodology-and-roadmap-only change. Runner support for
`--critique-pass`, twin-leaderboard rendering, and the result-JSON
`critique_pass` field land in a follow-up code PR before v0.5 ships.
v0.4 results remain the headline numbers until that PR lands and a
fresh bench pass runs.

---

## [v0.4.0] - 2026-05-08

Provider-coverage expansion plus a small methodology PATCH (0.1 to 0.1.1)
introducing the `model_class` field so reasoning and search-augmented
models are not silently ranked alongside standard chat models.

### Providers (was 8, now 27)

PRICING_TABLE expanded from 8 to 27 entries across 6 providers. All values
checked against the LiteLLM pricing catalog and provider docs where
available; entries marked UNVERIFIED in the v0.4 PR comment are pulled
from provider-page screenshots and should be re-verified before headline
publication.

- **xAI Grok via api.x.ai/v1** (4 entries): grok-4, grok-4-fast, grok-3,
  grok-3-mini.
- **Perplexity Sonar via api.perplexity.ai** (4 entries): sonar, sonar-pro
  (both `model_class="search"`); sonar-reasoning, sonar-reasoning-pro
  (both `model_class="reasoning"`). Per-search costs (about $5 per 1k
  searches) are NOT yet captured in TCoT for `search` class; v0.5 will add
  search-cost accounting.
- **OpenAI o-series** (3 entries): o3, o3-mini, o4-mini. All
  `model_class="reasoning"`. Adapter detects o-series by the `o<digit>`
  prefix and switches to `max_completion_tokens` plus default temperature
  to satisfy the o-series API contract.
- **OpenRouter via openrouter.ai/api/v1** (8 entries): meta-llama/llama-4-maverick,
  meta-llama/llama-4-scout, meta-llama/llama-3.3-70b-instruct,
  deepseek/deepseek-chat, deepseek/deepseek-r1 (`model_class="reasoning"`),
  mistralai/mistral-large, cohere/command-r-plus, qwen/qwen-3-235b-a22b.

### Methodology (v0.1 to v0.1.1, PATCH bump)

- **`model_class` field** on `Pricing` (METHODOLOGY s2.7). Three values:
  `standard` (default; conventional chat completion), `reasoning` (explicit
  thinking-budget output tokens; output costs include thinking tokens, so
  absolute `effective_TCoT` runs 5x to 20x higher per task than non-reasoning
  peers), `search` (retrieval-augmented; per-query knowledge varies; per-search
  costs not yet captured in TCoT). Additive with a safe default, hence PATCH.
- s11 versioning rule clarified: additive pricing fields with safe defaults
  qualify as PATCH.
- The leaderboard renderer surfaces `model_class` as an inline chip and
  groups the cross-task ranking matrix by class so within-class ranking is
  the primary procurement signal. Cross-class ranking misleads (reasoning
  burns more output tokens, search has unmetered per-search fees).

### OpenAI-compatible adapter generalization

- `OpenAIAdapter.__init__` now accepts `base_url` and `api_key_env_var`,
  letting xAI, Perplexity, and OpenRouter share the OpenAI Chat Completions
  wire protocol without a new adapter class. `OPENAI_API_KEY` remains the
  default env var; per-provider keys (`XAI_API_KEY`, `PERPLEXITY_API_KEY`,
  `OPENROUTER_API_KEY`) are wired through the CLI registry.
- O-series carve-out for OpenAI proper only: `temperature` is omitted and
  `max_tokens` becomes `max_completion_tokens`. OpenAI-compatible vendors
  (xAI, Perplexity, OpenRouter routing DeepSeek R1) accept the normal
  parameter convention transparently and are NOT subject to the carve-out.

### Runner

- `_write_result` filename now includes a sanitized model_id segment:
  `<task>__<model>__<sha7>.json`. Required because OpenRouter routes 8
  distinct models under `provider_id="openrouter"` and they would otherwise
  collide on disk. Slashes and colons in model_ids are replaced with
  underscores. Backward-compatible at read time (`build.py` rglobs all
  JSONs); only new files use the longer naming.
- Result records carry `provider.model_class` so the leaderboard renderer
  can surface it without needing to look up pricing at site-build time
  (the lookup remains as a fallback for pre-v0.1.1 result files).

### CLI

- `_PROVIDER_REGISTRY` entry shape changes to `(adapter_class, provider_id,
  model_id, adapter_kwargs)` so OpenAI-compatible vendors can supply their
  `base_url` plus `api_key_env_var` without polluting the registry value
  shape with empty positional fields.
- Six provider-name aliases now: `anthropic`, `openai`, `google`, `xai`,
  `perplexity`, `openrouter`. `--provider all` iterates the 27 distinct
  (provider, model) entries.

### Site

- Class chip rendered next to each model name across the index, the cost
  calculator, and the per-task pages. Standard is shown low-contrast (the
  default) and reasoning/search are color-tinted (purple, amber). Glossary
  page documents the chip and links back to methodology s2.7.
- Cross-task ranking matrix groups rows by `model_class` (standard, then
  reasoning, then search) and sorts within class by average rank.
- Provider color swatches added for xAI (gray), Perplexity (teal),
  OpenRouter (orange).

### Tests

150 passing (was 144). New tests cover: 27-entry table shape across 6
providers, reasoning/search classification, default `model_class` is
`standard`, OpenAI o-series adapter calling convention, OpenAI-compatible
vendors keep the normal parameter convention, base_url plus
api_key_env_var threading.

---

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
