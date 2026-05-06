# Contributing

Bellwether is methodology-first; the toolkit exists to prove the methodology.
Contributions that strengthen either are welcome.

## Development setup

```bash
git clone https://github.com/cartesianxr7/bellwether
cd bellwether
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env       # add API keys for benchmark runs
pre-commit install         # if pre-commit is installed (see HANDOFF s10)
pytest                     # 120+ tests; all should pass
```

API keys are only needed for `bellwether run`. All unit tests use mocked
SDK clients, so `pytest` works without keys and is what CI runs.

## Adding a task

A task is a Python class satisfying the `Task` Protocol in
`src/bellwether/protocols.py`. See `src/bellwether/tasks/structured_extraction.py`
for the reference implementation. Required surface:

- `name`, `description`, `dataset_version`
- `canonical_prompt_template` (one prompt, all providers)
- `dataset_loader()` yields `Example` instances with `prompt_inputs` and `ground_truth`
- `validator(output, ground_truth) -> ValidationResult`

Validators MUST follow METHODOLOGY s3: `failure_reason` stays at the
schema or format level, never echoes the ground truth, never quotes
expected values, never names content-level deltas. Any path that leaks
ground truth into the retry prompt invalidates the bench.

Register the class in `src/bellwether/tasks/__init__.py` and
`src/bellwether/cli.py:_TASK_REGISTRY`. Add tests in `tests/test_<task>.py`
covering: exact-match success, schema-break failure, partial credit,
and a ground-truth-leak check on `failure_reason`.

## Adding a provider adapter

A provider adapter implements the `ProviderAdapter` Protocol. References:
`src/bellwether/providers/{anthropic,openai,google}.py`. Required surface:

- `provider_id: str`, `model_id: str`
- `call(prompt: str, max_tokens: int) -> ProviderResponse`

Adapters MUST catch SDK exceptions and surface them via
`ProviderResponse.error` rather than propagating; the runner classifies
these as `FailureMode.ERROR` and records the latency observation.

Normalize the provider's `finish_reason` to the common vocabulary:
`stop`, `length`, `content_filter`, `tool_use`.

Add a pricing entry for each `(provider, model)` you support in
`src/bellwether/pricing.py`. Include the source URL and `as_of` date.
Wrong pricing means wrong `effective_TCoT` means the leaderboard
misranks; verification is part of the deliverable.

Register in `src/bellwether/cli.py:_PROVIDER_REGISTRY`. Add a test file
that mocks the SDK client (no real API calls in tests).

## Methodology versioning

Methodology version is in `METHODOLOGY.md` (header) and
`src/bellwether/__init__.py` (`__methodology_version__`). Per
METHODOLOGY s11:

- **MAJOR** bump: breaking changes to formulas (`TCoT`, `effective_TCoT`)
  or failure-mode semantics. Old results become non-comparable; require
  re-run.
- **MINOR** bump: new task contract fields, additive failure modes, new
  validators.
- **PATCH** bump: bugfix to validators, pricing updates, doc edits.

## Honest reporting

The point of bellwether is honest numbers. METHODOLOGY s12 has the full
checklist. Briefly: show all providers (no hiding losers), surface
`success_rate < 1.0` prominently, link failure-mode breakdowns, mark
dirty-tree results as non-headline, mark ranks within 1 std as tied.

If a change you propose would weaken any of those, please open an issue
first to discuss the trade-off.

## Testing

```bash
pytest                # all tests
pytest -v             # verbose
pytest tests/test_tcot.py        # one file
pytest -k effective_tcot         # by name
ruff check src tests             # lint
```

## Local benchmarks

```bash
bellwether list providers
bellwether list tasks
bellwether run --task=structured_extraction --provider=anthropic --instances 5 --max-cost 1
bellwether report results       # re-print leaderboard from existing data
```

The cost guardrail (`--max-cost USD`) is a hard cap on total spend per
invocation. Strongly recommended.
