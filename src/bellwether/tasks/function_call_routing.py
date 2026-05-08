"""Task #2: function-call routing (synthetic).

Procurement scenario: agentic LLMs are routinely given a registry of tools
and asked to pick the right one for a user query, with the right argument
values. This task measures both: tool selection AND argument construction.

- Score 1.0: correct tool AND correct arguments (passes).
- Score 0.5: correct tool, wrong arguments (PARTIAL).
- Score 0.0: wrong tool (CONFABULATION).
- SCHEMA_BREAK: output is not a valid JSON object with 'tool' and 'arguments'.

Synthetic generator avoids the BFCL dataset dependency for v0.x; the
real-dataset upgrade (BFCL pinned to a release commit) lands in v1.

failure_reason follows METHODOLOGY s3 (schema/format level only). The tool
registry is in the prompt, so naming "tool" or "arguments" leaks nothing.
"""

from __future__ import annotations

import json
import random
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from bellwether.protocols import Example, ValidationResult
from bellwether.taxonomy import FailureMode

_TOOL_REGISTRY_TEXT = """\
- get_weather(location: string) - Get current weather for a location.
- send_email(to: string, subject: string) - Send an email.
- search_web(query: string, num_results: integer) - Search the web for information.
- create_calendar_event(title: string, date: string) - Create a calendar event.
- translate_text(text: string, target_language: string) - Translate text to another language.
- get_stock_price(ticker: string) - Get current stock price for a ticker symbol.
"""

_CANONICAL_PROMPT = """\
You have access to the following tools:

{tool_registry}

User query: "{query}"

Pick the most appropriate tool. Output ONLY a JSON object in this exact format:
{{"tool": "tool_name", "arguments": {{"arg_key": "arg_value"}}}}

The "arguments" object must contain exactly the parameters that tool requires,
with values inferred from the user query. Use the exact key names from the tool
signature. For numeric parameters output JSON numbers (not strings).

Output ONLY the JSON object. No prose, no code fences, no commentary.
"""


def _gen_get_weather(rng: random.Random) -> dict[str, Any]:
    city = rng.choice(
        ["Paris", "Tokyo", "Cairo", "Sydney", "Reykjavik", "Mexico City", "Cape Town"]
    )
    return {
        "query": f"What is the weather in {city}?",
        "ground_truth": {"tool": "get_weather", "arguments": {"location": city}},
    }


def _gen_send_email(rng: random.Random) -> dict[str, Any]:
    to = rng.choice(["alice@example.com", "bob@example.com", "team@example.com"])
    subj = rng.choice(["Meeting tomorrow", "Q3 numbers", "Project update"])
    return {
        "query": f'Send an email to {to} with subject "{subj}"',
        "ground_truth": {"tool": "send_email", "arguments": {"to": to, "subject": subj}},
    }


def _gen_search_web(rng: random.Random) -> dict[str, Any]:
    q = rng.choice(["llm benchmarks", "python testing best practices", "design system tokens"])
    n = rng.choice([3, 5, 10])
    return {
        "query": f"Search for {q}, give me {n} results.",
        "ground_truth": {"tool": "search_web", "arguments": {"query": q, "num_results": n}},
    }


def _gen_calendar_event(rng: random.Random) -> dict[str, Any]:
    title = rng.choice(["Standup", "1:1 with manager", "Demo prep"])
    month = rng.randint(1, 12)
    day = rng.randint(1, 28)
    date = f"2026-{month:02d}-{day:02d}"
    return {
        "query": f'Create a calendar event titled "{title}" on {date}.',
        "ground_truth": {
            "tool": "create_calendar_event",
            "arguments": {"title": title, "date": date},
        },
    }


def _gen_translate(rng: random.Random) -> dict[str, Any]:
    text = rng.choice(["hello", "thank you", "goodbye"])
    lang = rng.choice(["French", "Japanese", "German"])
    return {
        "query": f'Translate "{text}" to {lang}.',
        "ground_truth": {
            "tool": "translate_text",
            "arguments": {"text": text, "target_language": lang},
        },
    }


def _gen_stock_price(rng: random.Random) -> dict[str, Any]:
    tic = rng.choice(["AAPL", "GOOGL", "MSFT", "NVDA", "META"])
    return {
        "query": f"What is the current stock price of {tic}?",
        "ground_truth": {"tool": "get_stock_price", "arguments": {"ticker": tic}},
    }


_GENERATORS = (
    _gen_get_weather,
    _gen_send_email,
    _gen_search_web,
    _gen_calendar_event,
    _gen_translate,
    _gen_stock_price,
)


@dataclass
class FunctionCallRoutingTask:
    """Synthetic function-call routing. Implements bellwether.protocols.Task."""

    name: str = "function_call_routing"
    description: str = (
        "Pick the right tool from a fixed registry and construct correct "
        "arguments from a user query. Synthetic; deterministic."
    )
    canonical_prompt_template: str = _CANONICAL_PROMPT
    tuned_prompt_templates: dict[str, str] = field(default_factory=dict)
    max_attempts: int = 3
    timeout_seconds: int = 30
    pass_threshold: float = 1.0
    license: str = "synthetic-no-redistribution-required"
    n_instances: int = 5
    seed: int = 42

    @property
    def dataset_version(self) -> str:
        return f"synthetic-fc-routing-v1-seed{self.seed}-n{self.n_instances}"

    def dataset_loader(self) -> Iterable[Example]:
        rng = random.Random(self.seed)
        for i in range(self.n_instances):
            gen = rng.choice(_GENERATORS)
            inst = gen(rng)
            yield Example(
                instance_id=f"fc-{i:04d}",
                prompt_inputs={
                    "tool_registry": _TOOL_REGISTRY_TEXT,
                    "query": inst["query"],
                },
                ground_truth=inst["ground_truth"],
            )

    def validator(self, output: str, ground_truth: Any) -> ValidationResult:
        parsed = _parse_json_object(output)
        if isinstance(parsed, _ParseError):
            return ValidationResult(
                passed=False,
                score=0.0,
                failure_reason=parsed.message,
                failure_modes=[FailureMode.SCHEMA_BREAK],
            )

        if "tool" not in parsed or "arguments" not in parsed:
            return ValidationResult(
                passed=False,
                score=0.0,
                failure_reason="missing required field(s): tool, arguments",
                failure_modes=[FailureMode.SCHEMA_BREAK],
            )

        if not isinstance(parsed["arguments"], dict):
            return ValidationResult(
                passed=False,
                score=0.0,
                failure_reason="'arguments' must be a JSON object",
                failure_modes=[FailureMode.SCHEMA_BREAK],
            )

        tool_match = parsed["tool"] == ground_truth["tool"]
        args_match = parsed["arguments"] == ground_truth["arguments"]

        if tool_match and args_match:
            return ValidationResult(passed=True, score=1.0)

        if tool_match:
            return ValidationResult(
                passed=False,
                score=0.5,
                failure_reason="tool selection correct but argument values did not match",
                failure_modes=[FailureMode.PARTIAL],
            )

        return ValidationResult(
            passed=False,
            score=0.0,
            failure_reason="tool selection did not match expected",
            failure_modes=[FailureMode.CONFABULATION],
        )


@dataclass
class _ParseError:
    message: str


def _parse_json_object(output: str) -> dict[str, Any] | _ParseError:
    stripped = output.strip()
    if not stripped:
        return _ParseError("output is empty")
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        return _ParseError(
            f"json parse error at line {exc.lineno} col {exc.colno}: {exc.msg}"
        )
    if not isinstance(parsed, dict):
        return _ParseError(f"expected JSON object, got {type(parsed).__name__}")
    return parsed
