# Bellwether Methodology

**Status:** Locked v0 draft. Update via PR plus version bump.
**Methodology version:** 0.1
**Last updated:** 2026-05-05

> The methodology is Bellwether's primary contribution. The leaderboard is its proof of work. Anyone disagreeing with the numbers must engage with this doc, not the table.

---

## 1. Core principles

1. **The methodology is the contribution.** The leaderboard is its proof. Disagreements must engage with this doc.
2. **Reproducibility, with bounded stochasticity.** Same code plus same model version plus same dataset = same results within provider non-determinism bounds. T=0 reduces stochasticity but does not eliminate it; we report `mean +/- std` across N runs (see s7) rather than claim byte-identity.
3. **No LLM-as-judge.** Validation is mechanically checkable. Schema, regex, exact match, F1 against fixed ground truth.
4. **No per-provider prompt tuning in headline numbers.** One canonical prompt per task. (Tuned track exists separately for comparison, never for the leaderboard.)
5. **Honest reporting.** All raw outputs preserved. Failures categorized. Costs reported including failed-attempt waste. If a provider loses, we say so.

## 2. Total Cost of Task (TCoT)

> The cost to *reliably complete a task end-to-end*, including retries and validation loops.

### 2.1 Formula

For a single task instance attempted by provider *P*:

```
TCoT(P, instance) = sum over attempts a in [1..max_attempts]:
                      input_tokens(a)  * input_price_per_token(P)
                    + output_tokens(a) * output_price_per_token(P)
                    until validation passes OR max_attempts reached
```

### 2.2 Outcomes

For a given task instance:
- **`success`**: validation passed within `max_attempts`. `TCoT_success` = sum of all attempt costs up to the passing attempt.
- **`failure`**: validation never passed. `TCoT_failure` = sum of all attempt costs across all `max_attempts`. The failed work still costs money. It counts.

### 2.3 Aggregate metrics (per provider x task, over N instances)

| Metric | Formula | Interpretation |
|---|---|---|
| `success_rate` | (passing instances) / N | Reliability under the standard retry loop |
| `mean_TCoT_success` | mean over passing instances | Cost per successful completion |
| `mean_TCoT_failure` | mean over failing instances | Cost of wasted work |
| `effective_TCoT` | `mean_TCoT_success + mean_TCoT_failure * (1 - success_rate) / success_rate` | **Headline metric.** Total spend per successful completion, including failed-attempt waste amortized across the successes. Equivalent to `(total_spend_across_all_instances) / num_successes`. |
| `mean_latency_p50` | median wall-clock per attempt | |
| `mean_latency_p95` | 95th percentile wall-clock per attempt | |

`effective_TCoT` is the metric we publish in the leaderboard. It captures both efficiency (cheaper attempts win) and reliability (each failure forces successes to amortize the wasted spend). Worked example: provider A completes 100% of attempts at $0.002/success; provider B completes 50% at $0.001/success but burns $0.003 on each failure (3 retries before giving up). `effective_TCoT_A = 0.002`. `effective_TCoT_B = 0.001 + 0.003 * (0.5 / 0.5) = 0.004`. Reliability dominates as failure rate rises and as failure costs diverge from success costs. The naive shorthand `mean_TCoT_success / success_rate` undercounts because it implicitly assumes `mean_TCoT_failure == mean_TCoT_success`, which is rarely true: failures usually consume all `max_attempts` while successes often pass on attempt 1.

### 2.4 What's included

- All API token costs across all retries.
- All API token costs across failed attempts that didn't lead to success.

### 2.5 What's excluded (and why)

- **Compute cost of running the harness itself**: negligible, not provider-attributable.
- **Network egress**: negligible, not provider-attributable.
- **Engineering time**: out of scope; users can model this separately.
- **Validator costs**: in v0 we use only machine-checkable validators (validator cost = $0). If LLM-validators are ever introduced (v1+), validator costs MUST be added to TCoT for the validating provider.

### 2.6 Provider price changes

Pricing tables live in `src/bellwether/pricing.py`, versioned with the package. Pricing is loaded once at run-start and frozen for the run; no provider exposes a public pricing API, so mid-run price changes go undetected by the harness. Each result JSON records the pricing version used; `pricing.py` comments link the dated provider-pricing page that informed each entry, for audit trail. If a provider changes prices between two runs, results from the two pricing versions are NOT averaged: they are reported as separate dated runs.

## 3. Retry policy

- **Default `max_attempts = 3`** (configurable per task).
- **On validation failure:** retry with the same canonical prompt plus a structured "your previous response failed validation: `<reason>`. Please correct and try again." appended as a new user-turn message. The original assistant turn(s) remain in context.
- **`<reason>` is constrained to schema and format level only.** Allowed: missing required field names from the declared schema, parser/JSON errors, `finish_reason` from the provider, length-limit hits. **Forbidden: any echo of expected values, named missing entities, F1 deltas, score values, or quoted ground truth.** Validators that emit content-level reasons leak ground truth and invalidate the run.
- This is a deliberately simple repair strategy. Production systems use more sophisticated repair; we benchmark BASE model reliability under a STANDARD repair loop. That's the apples-to-apples test.
- **No prompt rewriting between retries.** No chain-of-thought injection between retries. No per-provider retry hacks. Same loop for everyone.
- **After `max_attempts`:** outcome = `failure`, classify failure mode, record final attempt's output. Move on.

## 4. Validation policy

Per-task validators are pure functions: `validate(output: str, ground_truth: Any) -> ValidationResult`.

```python
@dataclass
class ValidationResult:
    passed: bool                       # True iff score >= the task's pass_threshold
    score: float                       # in [0, 1]; may be partial credit
    failure_reason: str | None         # schema/format level only; see s3 retry policy
    failure_modes: list[FailureMode]   # taxonomic, empty if passed
```

`pass_threshold` is a task-level constant defined on `Task` (see s8), not stored on each `ValidationResult`. Storing it per-result invites per-instance drift.

Validators MUST be:
- **Deterministic** (same input gives same output).
- **Implementable without an LLM** (no API calls, no model loading).
- **Documented** in the task's docstring with examples.
- **Unit-tested** with both passing and failing fixtures.

## 5. Failure-mode taxonomy

Every failure (`passed = False`) is classified into one or more modes. Multiple modes per failure allowed (e.g. `[CONFABULATION, PARTIAL]`).

| Mode | Definition | Detection in v0 |
|---|---|---|
| `REFUSAL` | Model declined to attempt the task | Output matches refusal regex bank ("I can't", "I won't", "as an AI", "I'm not able to", etc.); score = 0 |
| `CONFABULATION` | Output is fluent and well-formatted but factually wrong or fabricated | Passes format/schema checks, fails content checks (exact match, F1, fact-check against ground truth) |
| `SCHEMA_BREAK` | Output is malformed (invalid JSON, wrong structure, missing required fields) | Output fails parser/schema validation |
| `TRUNCATION` | Output cut off mid-response | Final token is mid-word OR `finish_reason == "length"` from the provider |
| `OFFTASK` | Output is on-topic but answers a different question than asked | Format OK; content addresses something other than the task instance (low overlap with expected key entities) |
| `PARTIAL` | Output partially correct (some fields right, others wrong; or partial F1) | `0 < score < pass_threshold` |
| `TIMEOUT` | Provider exceeded wall-clock budget | Attempt aborted after `task_timeout_seconds` |
| `ERROR` | Provider returned an API error | HTTP error, rate limit, content filter trip, etc. Recorded with the error class. |

> Detection is best-effort and conservative. **In v0, `OFFTASK` and `CONFABULATION` collapse in practice** because v0 datasets do not ship per-instance "expected key entities" annotations needed to distinguish them; classifiers default to `CONFABULATION` for content failures and reserve `OFFTASK` for the rare case where a manual annotation is available. The taxonomy improves as we collect more data. v0 is a starting point, not a final ontology.

## 6. Prompt portability

Each task can carry TWO prompt tracks:

1. **Canonical** (used for headline / leaderboard numbers): the single prompt used across ALL providers without modification. Designed to be reasonable for any modern instruct-tuned LLM. No provider name, no model-specific tokens, no provider-favoring tricks.
2. **Tuned** (v1 feature, NOT in v0): per-provider optimized prompt. Reported alongside canonical results in a "tuned delta" column once shipped.

**v0 ships canonical only.** `tuned_prompt_templates` defaults to an empty dict; the leaderboard renders no "tuned delta" column. Operationalizing the tuned track requires a contract that v0 does not yet have: who tunes, with what compute budget, against which validation split, to what convergence criterion. v1 will define and publish that contract before populating tuned numbers. Any v0 result claiming tuned-track numbers is a bug.

The eventual DELTA between canonical and tuned per provider is the **portability cost**: how much performance you leave on the table by not tuning per provider. This is the number an enterprise CE actually wants when a customer asks "what is the lift to swap from GPT to Gemini?"

## 7. Stochasticity and multi-run

- **Default temperature: 0** where supported (Gemini, GPT, Claude all support). **T=0 minimizes stochasticity but does not guarantee determinism.** All three providers exhibit backend non-determinism even at T=0 due to batch effects and floating-point non-associativity on GPU; Anthropic documents this explicitly. Treat T=0 as a noise-reduction default, not a reproducibility guarantee.
- **Default `N` runs per (task instance x provider): 3** in v0 (cheap; minimal stats).
- For `N > 1`: report `mean +/- std` for all aggregate metrics. **The leaderboard visually marks ranks within 1 std of each other as tied**; with N=3 the noise floor is high and small gaps are not significant.
- For `N = 1` results, the JSON includes a `"single_run": true` flag and the leaderboard renders them with a caveat.
- v1 will expand to `N=5+` with bootstrap confidence intervals.

## 8. Per-task contract

Every task in `bellwether/tasks/` MUST provide:

```python
class Task(Protocol):
    name: str                                              # unique identifier (e.g. "structured_extraction")
    description: str                                       # one-paragraph description
    dataset_version: str                                   # version/checksum recorded per result for reproducibility (s9)
    dataset_loader: Callable[[], Iterable[Example]]        # yields task instances with ground truth
    canonical_prompt_template: str                         # one prompt, all providers (Jinja-style placeholders)
    tuned_prompt_templates: dict[ProviderId, str]          # optional per-provider tuning, default: {}
    validator: Callable[[output: str, ground_truth: Any], ValidationResult]
    max_attempts: int = 3
    timeout_seconds: int = 30
    pass_threshold: float = 1.0                            # task-specific
    license: str                                           # dataset license; must be redistribution-compatible OR loadable by reference
```

Tasks failing the contract are rejected at collection time. Runner refuses to bench them.

## 9. Reproducibility guarantees

Every benchmark run records, per attempt:

```json
{
  "bellwether_version": "0.1.0",
  "methodology_version": "0.1",
  "git_sha": "abc1234",
  "git_dirty": false,
  "pricing_version": "2026-05-05",
  "provider": {
    "id": "gemini",
    "model_id": "gemini-2.0-flash-001",
    "model_version_hint": "from API where exposed"
  },
  "task": {
    "name": "structured_extraction",
    "instance_id": "...",
    "dataset_version": "sha or checksum"
  },
  "attempt": 1,
  "prompt": "...",
  "output": "...",
  "input_tokens": 1234,
  "output_tokens": 567,
  "cost_usd": 0.001234,
  "latency_seconds": 1.2,
  "validation": { "passed": true, "score": 1.0, "failure_modes": [] }
}
```

Re-running with the same versions produces results within stochasticity bounds. T=0 reduces but does not eliminate non-determinism (see s7); we do NOT claim byte-identity. The runner refuses to write results from a dirty git tree unless `--allow-dirty` is passed; the `git_dirty` field reflects the tree state at run-start. Dirty results are flagged in the leaderboard and excluded from headline aggregates.

## 10. What this benchmark does NOT measure (in v0)

- **Subjective output quality** ("is this answer beautifully written?")
- **Capability on tasks without machine-checkable ground truth**
- **Multi-turn dialogue quality**
- **Adversarial robustness / jailbreaks**
- **Bias / fairness** (separate evaluation domain, not our remit)
- **Cost at scale** (we measure unit cost; users extrapolate)

We say so explicitly to prevent over-claims.

## 11. Versioning

- This methodology versions with the package. `methodology_version` recorded in every result JSON.
- **MAJOR** bump = breaking changes to formulas (TCoT, effective_TCoT) or taxonomy semantics. Old results are NOT comparable; require re-run.
- **MINOR** bump = new task contract fields, new failure modes (additive only), new validators.
- **PATCH** = bugfix to validators, pricing updates, doc edits.

## 12. Honest reporting checklist (every results page)

- [ ] All providers shown for all tasks (no hiding losers).
- [ ] `success_rate < 1.0` shown prominently, not buried.
- [ ] Failure-mode breakdown linked from every cell.
- [ ] Methodology version and git SHA on every page.
- [ ] Date of run and pricing version visible.
- [ ] Per-attempt raw outputs linked from each result.
- [ ] "Where each provider wins" section is honest: no rigging the categorization.
- [ ] Ranks within 1 std visually marked as tied (see s7); small leaderboard gaps at N=3 are noise, not signal.
- [ ] Any results from a dirty git tree (`git_dirty: true`) flagged and excluded from headline aggregates (see s9).
