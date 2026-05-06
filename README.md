# bellwether

[![tests](https://github.com/cartesianxr7/bellwether/actions/workflows/test.yml/badge.svg)](https://github.com/cartesianxr7/bellwether/actions/workflows/test.yml)
[![python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://github.com/cartesianxr7/bellwether)
[![methodology](https://img.shields.io/badge/methodology-v0.1-blueviolet.svg)](https://cartesianxr7.github.io/bellwether/methodology.html)
[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

The cost-and-failure-mode benchmark for LLM agents. Methodology plus Python package for honest, reproducible cross-provider agent evaluation.

**[Live leaderboard](https://cartesianxr7.github.io/bellwether/)** &middot; **[Methodology](https://cartesianxr7.github.io/bellwether/methodology.html)**

## Why

Cross-provider LLM benchmarks today rank capability ("which model is smarter on average"). HELM and Chatbot Arena own that ground.

Practitioners building production systems need a different answer: **which provider for THIS task, at THIS cost when retries and failures are accounted for, with THESE failure modes that map to my product's tolerance.**

bellwether answers the procurement question and ships the toolkit anyone can run on their own prompts.

## What it measures

- **`effective_TCoT`**: total cost per successfully completed task, including the cost of failed retries. The procurement-question metric, not the average-quality one.
- **Failure-mode taxonomy**: classify *how* models fail, not just whether (refusal, confabulation, schema break, truncation, partial, off-task, timeout, error). Maps to product-tolerance decisions.
- **Machine-checkable ground truth only.** No LLM-as-judge. Sidesteps the well-documented judge-bias issue.
- **Prompt portability.** Headline numbers use one canonical prompt across providers; portability cost (tuned vs canonical) is a v1 promise with a real contract.

See [METHODOLOGY.md](METHODOLOGY.md) for formulas, retry policy, validator contract, and reproducibility caveats.

## Install

From source (current; PyPI publish pending):

```bash
git clone https://github.com/cartesianxr7/bellwether
cd bellwether
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env       # add ANTHROPIC_API_KEY, OPENAI_API_KEY, GOOGLE_API_KEY
pre-commit install         # optional, gates secret leaks
pytest                     # 120+ tests; all should pass
```

After v0.1.0 publish to PyPI:

```bash
pip install bellwether
```

## Run

```bash
bellwether list providers           # show registered provider adapters
bellwether list tasks               # show registered tasks

# Smoke test: 2 instances, 1 run each, $1 cap, takes ~10 seconds and ~$0.01:
bellwether run --instances 2 --n 1 --max-cost 1

# Standard bench: 5 instances, 3 runs per instance, all 3 providers, $5 cap:
bellwether run --instances 5 --n 3 --max-cost 5

# Re-render leaderboard from existing results without re-running:
bellwether report results
```

The cost guardrail (`--max-cost USD`) is a hard cap on total spend per invocation. Strongly recommended.

## Status

**v0.1**: methodology, package, CLI, structured-output extraction task across Claude Sonnet 4.6, GPT-4o, and Gemini 2.5 Flash Lite. 1-task leaderboard, 3-pass reproducibility data.

**v0.2 through v0.5**: function calling (BFCL), RAG (FinanceBench/NQ-open/HotpotQA), multi-step reasoning (GAIA validation set), long-context summarization (GovReport). One task per release.

**v1**: code-generation task with sandboxing, OpenRouter open-weights, tuned-prompt-track formalization, plugin loader.

## Repository

- Code: [github.com/cartesianxr7/bellwether](https://github.com/cartesianxr7/bellwether)
- Leaderboard: [cartesianxr7.github.io/bellwether](https://cartesianxr7.github.io/bellwether)
- Methodology: [cartesianxr7.github.io/bellwether/methodology.html](https://cartesianxr7.github.io/bellwether/methodology.html)
- Raw results JSON: [results/](https://github.com/cartesianxr7/bellwether/tree/main/results)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Adding a task or a provider adapter is a single PR; the contract is documented and small.

## License

MIT. See [LICENSE](LICENSE).

## Author

Stephen Hedrick.
