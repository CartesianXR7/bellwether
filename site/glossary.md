# Glossary

Plain-English definitions of every term that appears on the leaderboard or in
the methodology. For formal definitions see [METHODOLOGY](methodology.html).

## Headline metrics

### `effective_TCoT`

The total cost of getting one task done **successfully**, including the cost
of every failed attempt that happened along the way before the model finally
got it right (or before retries were exhausted).

A provider that is cheap per call but fails often can have a *higher*
`effective_TCoT` than a provider that costs more per call but succeeds first
try. That trade-off is the whole point of the metric.

Lower is better. Reported in USD.

### Success rate

Out of every (instance, run) trial benched, the fraction that produced a
validator-passing result within the configured `max_attempts` retry budget.
Shown as percentage and absolute count.

### Latency p50 / p95

Per-API-call wall-clock time, in seconds. p50 is the median; p95 is the 95th
percentile (the slow tail). Tracks all attempts across all trials, not just
successful ones.

### 1st-try pass rate

Of every trial, the fraction that passed validation on its very first attempt
(no retries needed). High first-try-pass means the provider is well-calibrated
to the prompt; low first-try-pass means the retry loop is doing real work.

## Failure modes

The eight categories every failed attempt is classified into. Multiple modes
per failure are allowed (e.g. `truncation` plus `refusal`).

### `refusal`

The model declined to attempt the task ("I can't help with that," "as an AI
assistant," etc.). Detected by regex against a bank of common refusal phrases;
only counted on attempts that also fail validation.

### `confabulation`

The model produced fluent, well-formatted output that was factually wrong or
fabricated. Passes format/schema checks but fails content checks. The
default classification for content-level failures that are not also schema
breaks.

### `schema_break`

The output did not parse as the expected structure: invalid JSON, wrong
shape, missing required fields, etc. Recoverable by retry in many cases;
provider's structured-output discipline.

### `truncation`

The output was cut off mid-response, either because the provider returned
`finish_reason == "length"` or because the visible end of the output is a
half-word with no terminal punctuation.

### `partial`

The output was partially correct: some required fields right, others wrong;
or partial F1 against ground truth. Score strictly between 0 and the
task's `pass_threshold`.

### `offtask`

The output was on-topic but answered a different question than the one asked.
In v0 this is hard to distinguish from `confabulation` because the synthetic
datasets do not ship per-instance "expected key entities" annotations needed
to tell them apart; v0 classifiers default to `confabulation` for content
failures.

### `timeout`

The provider did not return a response within the task's `timeout_seconds`
budget. The attempt was aborted and recorded as a timeout.

### `error`

The provider's API returned an error (HTTP 4xx/5xx, rate limit, content
filter trip, transport failure). The error class is recorded for audit.

## Status flags

### Dirty tree

A row marked with a leading `*` (or a `dirty tree` badge in the pass header)
came from a benchmark run where the source-code tree had uncommitted changes
at run-start. Per [methodology s9](methodology.html#9-reproducibility-guarantees),
dirty results are flagged and excluded from headline aggregates because they
cannot be tied to a known git commit.

### Tied within noise (≈)

A row marked with `≈` after its rank is within 5% of the rank above on
`effective_TCoT`. With N=3 runs per instance the headline metric carries
real noise; near-tied ranks should be read as ties, not as a meaningful
ordering. v0.4 will replace this heuristic with bootstrap confidence
intervals.

### `±` (standard deviation)

Reported next to `effective_TCoT` in the form `$0.00099 ±$0.00012`. The
±-value is the population stddev of per-trial cost across the successful
trials in this pass. Useful for spotting providers whose performance is
unusually variable; expect 0 when fewer than two successes were observed.

## Concepts in the methodology

### TCoT (Total Cost of Task)

The cost to *attempt* one task instance end-to-end, including every retry.
`effective_TCoT` then amortizes failed-attempt cost across the successes.
See [methodology s2](methodology.html#2-total-cost-of-task-tcot).

### `max_attempts`

The retry budget per (instance, run) trial. Default 3. After this many
attempts without a passing validation, the trial is recorded as a failure.

### Canonical prompt

The single prompt template used across **all** providers for headline
numbers, with no per-provider tweaking. The point is to measure cost and
failure modes under the same input the user actually controls. Per-provider
tuned prompts are a v1 feature; see methodology s6.

### Schema-only retry feedback

When a trial fails and is retried, the prompt that goes back to the model
includes a description of what went wrong, but only at the schema/format
level (e.g. "your output is not valid JSON"). It must never echo the
expected ground-truth values, or the bench is contaminated. Validators
that violate this rule invalidate their results. See methodology s3.

### Reproducibility (and why we don't claim byte-identity)

Same code + same model snapshot + same dataset *should* give the same
results. In practice it does not, even at temperature 0, because all
three providers exhibit backend non-determinism (batch effects, GPU
floating-point non-associativity). T=0 reduces stochasticity but does
not eliminate it; the methodology reports `mean ± std` across N runs
rather than claiming exact reproducibility. See methodology s7.
