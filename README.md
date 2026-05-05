# bellwether

The cost-and-failure-mode benchmark for LLM agents. Methodology plus Python package for honest, reproducible cross-provider agent evaluation.

## What it measures

- **`effective_TCoT`**: total cost per successfully completed task, including the cost of failed retries. The procurement-question metric, not the average-quality one.
- **Failure-mode taxonomy**: refusal, confabulation, schema break, truncation, partial, timeout, error. Pass/fail loses the signal a procurement decision actually needs.
- **Machine-checkable ground truth only.** No LLM-as-judge.
- **Prompt portability.** Headline numbers use one canonical prompt across providers.

See [METHODOLOGY.md](METHODOLOGY.md) for formulas, retry policy, validator contract, and reproducibility guarantees.

## Install

```bash
# After v0.1.0 publish:
pip install bellwether

# From source:
git clone https://github.com/cartesianxr7/bellwether
cd bellwether
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # fill in provider API keys
pre-commit install
pytest
```

## Run

```bash
bellwether list tasks
bellwether list providers
bellwether run --task=structured_extraction --provider=claude
bellwether report results/
```

## Status

**v0.1**: methodology, package, CLI, structured-output extraction task across Claude, Gemini, and GPT-4o. 1-entry leaderboard.

**v0.2 through v0.5**: function calling, RAG, multi-step reasoning, long-context summarization. One task per release.

**v1**: code-generation task with sandboxing, OpenRouter open-weights, tuned-prompt track, plugin loader.

## Repository

- Code: [github.com/cartesianxr7/bellwether](https://github.com/cartesianxr7/bellwether)
- Leaderboard: [cartesianxr7.github.io/bellwether](https://cartesianxr7.github.io/bellwether)

## License

MIT. See [LICENSE](LICENSE).

## Author

Stephen Hedrick.
