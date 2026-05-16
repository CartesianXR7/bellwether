# Roadmap

What is shipped, what is next, what is later. Methodology-version semantics
per [METHODOLOGY.md s11](METHODOLOGY.md#11-versioning).

## Shipped (v0.1, v0.3, v0.4)

### v0.1 (2026-05-06)
- Methodology v0.1 (corrected `effective_TCoT`, schema-only retry, taxonomy)
- Python package on PyPI
- Live leaderboard
- 1 task (structured_extraction), 3 providers (Sonnet 4.6 / GPT-4o / Gemini 2.5 Flash Lite)
- Cost guardrail, dirty-tree gate, per-provider rate limiter
- 120 tests, CI on Python 3.11/3.12/3.13, MIT license

### v0.3 (2026-05-07)
- 2 more tasks: `function_call_routing`, `synthetic_rag`
- 5 more provider models: Haiku 4.5, Opus 4.7, GPT-4o-mini, Gemini 2.5 Flash, Gemini 2.5 Pro
- All 8 pricing entries verified
- mean ± std reporting on `effective_TCoT` per s7
- Tied-rank ≈ marker for ranks within bench noise
- Per-task drill-down pages (failure-mode aggregates, all-pass detail, reproducibility)
- Inline cost calculator widget
- Glossary page
- CONTRIBUTING, CODE_OF_CONDUCT, ARCHITECTURE, ROADMAP, CHANGELOG, issue templates
- 144 tests, ruff lint clean

### v0.4 (2026-05-08)
- 17 more provider entries across 4 new providers: xAI Grok (4), Perplexity
  Sonar (4), OpenAI o-series (3), OpenRouter (8 open-weights + commercial).
  Total 27 entries across 6 providers.
- Methodology PATCH 0.1 to 0.1.1: `model_class` field (`standard`, `reasoning`,
  `search`) so reasoning and search models are not silently ranked alongside
  standard chat models. Site renders class chips and groups the cross-task
  ranking matrix by class.
- `OpenAIAdapter` generalized to take `base_url` and `api_key_env_var`,
  letting xAI / Perplexity / OpenRouter share one adapter class.
  o-series carve-out for OpenAI proper only.
- Runner result filenames include sanitized `model_id` so OpenRouter's
  8 models do not collide.
- 150 tests, ruff lint clean.

## Next (v0.5)

Theme: developer ergonomics, statistical rigor, plus the v0.2 methodology
track (Critique-Pass).

- **Critique-Pass evaluation track** (methodology v0.2, see METHODOLOGY s13).
  New `--critique-pass` runner flag wraps each attempt with a single-shot
  self-revision step using the locked canonical critique prompt. TCoT counts
  both legs per s2.1. Twin leaderboards per task page (critique-off,
  critique-on) plus a `critique_delta` column showing per-model change in
  `effective_TCoT` and `success_rate`. Procurement reading: "for this
  provider on this task, the critique pass costs +X% TCoT for +Y pp
  success rate." Negative deltas honestly reported.
- **Async runner.** Parallelize adapter calls across providers within a task;
  cuts wall-clock roughly proportional to provider count. Per-provider rate
  limiter stays per-provider; cost guardrail becomes thread-safe.
- **BYO task config.** TOML schema + `ConfigDrivenTask` that loads from
  `--task-config PATH`. Validator types: `json_field_match`, `exact_match`,
  `regex_match`, `schema_match`. JSONL data file pointer. Goal: a developer
  can benchmark on their own prompts without writing Python.
- **Plugin loader.** `--plugins-dir DIR` loads tasks/providers from
  arbitrary paths. Lets contributors ship in their own repos. Prerequisite
  for the v1 hosted-run service.
- **Bootstrap confidence intervals** on `effective_TCoT` to replace the
  v0.3 5%-ratio tied-rank heuristic.
- **Increased default N from 3 to 5** with the bootstrap CI infra in place.
- **More CLI ergonomics.** `--filter "success_rate>0.95"`, `--format json|md|csv`,
  `--sort eff_tcot|p50|p95`.
- **Per-instance / per-attempt drill-down pages** on the static site.
- **Search-cost accounting in TCoT** for `model_class="search"` entries
  (Perplexity Sonar). Per-search fees (about $5 per 1k) are currently
  excluded from TCoT; v0.5 closes the gap.
- **Tuned-prompt track formalization.** Real contract for who tunes,
  against which split, to what convergence criterion. Renders alongside
  canonical numbers as a "tuned delta" column. Without the contract, the
  track does not ship.
- **Historical leaderboard with trend lines.** Show how each provider's
  `effective_TCoT` and `success_rate` move over time across model
  snapshots. Inline SVG sparklines.
- **Automated re-bench on schedule.** GH Actions cron weekly, or on
  pricing-table updates.
- **One more synthetic task** (long-context summarization with key-fact
  recall, where key facts are deterministically generated rather than
  LLM-extracted).

## v1 (DO NOT BUILD YET)

Theme: real datasets, open-weights, larger surface.

- **Code-generation task with sandboxing.** HumanEval+ or LiveCodeBench
  tier-easy. Requires Docker / firejail / seatbelt isolation; sandboxing
  IS the v1 work, not the task plumbing.
- **Multimodal `document_extraction_ocr` task.** Real-world document OCR
  on a redistribution-compatible open corpus (candidates: FUNSD, SROIE,
  CORD, or a curated public-domain receipts set; license check is the
  gating work). Tests handwriting, multi-column / table layouts, scan
  artifacts, JPEG compression, mixed text and graphics, multi-page.
  Validator reuses the `structured_extraction` exact-field-match
  contract so the delta between text-input and image-input isolates the
  OCR layer's contribution per provider. Methodology bump 0.2 to 0.3:
  - `pricing.py` gains image-input pricing per provider (OpenAI tiles,
    Anthropic per-image, Google per-pixel-class) with safe-default
    `None` for non-vision entries. Pricing schema extension is
    additive (PATCH-shaped data, bundled into the v1 minor for the
    new task).
  - New `modality: "text" | "image" | "text+image"` field on the Task
    protocol so the leaderboard filters cleanly.
  - Vision capability detected by attempt-and-classify, not a
    hardcoded `supports_vision` flag: non-vision providers error
    cleanly, recorded as `ERROR` failure mode, excluded from the OCR
    leaderboard without silent omission.
  Synthetic-render OCR was explicitly considered and rejected for v0.x
  per METHODOLOGY s10: clean methodology demo on synthetic PNGs does
  not answer the procurement question buyers actually have.
- **Real-dataset replacements** for the synthetic v0.x tasks:
  - BFCL pinned to a specific release commit
  - FinanceBench / NaturalQuestions-open / HotpotQA distractor (RAG)
  - GAIA validation set (multi-step reasoning)
  - GovReport (long-context summarization with manually annotated key facts)
- **OpenRouter for open-weights** (Llama, Mistral, Qwen). Adds a new
  provider class that routes through OpenRouter's unified API.
- **Adversarial / robustness tasks.** Out of scope for v0; needs careful
  methodology around what counts as a robustness failure.
- **Long-running agent tasks** (multi-hour, multi-step research).
  Stretches the runner significantly.
- **Custom-corpus RAG** (user-provided document set).
- **TOML/YAML config files** for full bench specifications, beyond
  per-task config.
- **Hosted run service.** POST a task spec, receive results JSON. Built
  on top of the plugin loader.

## Out of scope (intentional)

- Subjective-quality evaluation. The methodology requires machine-checkable
  ground truth.
- LLM-as-judge anywhere. Sidesteps the well-documented judge-bias issue.
- Capability rankings. HELM and Chatbot Arena exist; bellwether is the
  procurement-question complement, not a competitor.
- Real-time service-level guarantees on the leaderboard. Rebuilds happen
  manually after each bench pass; v0.5 adds scheduled re-bench but the
  leaderboard freshness is still bench-pass-driven, not real-time.

## How to influence this

- **Issues** with `methodology` or `enhancement` labels for changes
  upstream of code (formula proposals, taxonomy proposals, validator
  contract changes).
- **PRs** for new tasks or provider adapters following the contracts in
  [CONTRIBUTING.md](CONTRIBUTING.md). New tasks land in v0.x point releases;
  new providers land continuously.
- **Pricing table updates** are the easiest first contribution and the
  most operationally important; provider prices drift.
