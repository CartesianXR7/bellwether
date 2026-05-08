"""Task #3: synthetic RAG / single-fact retrieval.

Procurement scenario: read a passage, extract one specific fact. Tests
context-window reading and calibration on retrieval-style tasks. Pass/fail
is a case-insensitive exact match on the answer (after light normalization).

Synthetic generator avoids dataset dependencies (FinanceBench, NQ-open,
HotpotQA all have license or distribution constraints); the real-dataset
upgrade lands in v1 alongside the proper licensing review.

The synthetic passage is structured so the answer to the question is
verbatim present in exactly one sentence. A model that reads carefully
and answers without paraphrase passes; a model that paraphrases or
hallucinates fails. failure_reason stays schema/format-level per s3.
"""

from __future__ import annotations

import random
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from bellwether.protocols import Example, ValidationResult
from bellwether.taxonomy import FailureMode

_COMPANIES = (
    "Acme Corporation",
    "Globex Inc.",
    "Initech LLC",
    "Umbrella Holdings",
    "Stark Industries",
    "Wayne Enterprises",
    "Soylent Corp",
    "Cyberdyne Systems",
    "Massive Dynamic",
    "Tyrell Corporation",
)

_CEOS = (
    "Alice Walker",
    "Bob Chen",
    "Carol Singh",
    "David Okafor",
    "Elena Rossi",
    "Farhan Ahmed",
    "Grace Kim",
    "Hugo Sanchez",
)

_CITIES = (
    "Palo Alto",
    "Berlin",
    "Tokyo",
    "Singapore",
    "Stockholm",
    "Dubai",
    "Toronto",
    "Amsterdam",
)

_INDUSTRIES = (
    "technology",
    "finance",
    "manufacturing",
    "biotechnology",
    "energy",
    "logistics",
)

_TEMPLATES = {
    "ceo": "The CEO of {company} is {value}.",
    "founded": "{company} was founded in {value}.",
    "headquarters": "{company} is headquartered in {value}.",
    "industry": "{company} operates in the {value} industry.",
}

_QUESTIONS = {
    "ceo": "Who is the CEO of {company}?",
    "founded": "In what year was {company} founded?",
    "headquarters": "Where is {company} headquartered?",
    "industry": "In what industry does {company} operate?",
}

_CANONICAL_PROMPT = """\
Read the passage below carefully, then answer the question.

Output ONLY the answer text, exactly as it appears in the passage. Do not
paraphrase. Do not add prose or explanation. Do not wrap in quotes. Do not
add a trailing period.

Passage:
{passage}

Question: {question}

Answer:
"""


def _generate_attributes(rng: random.Random) -> dict[str, str]:
    return {
        "ceo": rng.choice(_CEOS),
        "founded": str(rng.randint(1960, 2015)),
        "headquarters": rng.choice(_CITIES),
        "industry": rng.choice(_INDUSTRIES),
    }


@dataclass
class SyntheticRagTask:
    """Synthetic single-fact retrieval. Implements bellwether.protocols.Task."""

    name: str = "synthetic_rag"
    description: str = (
        "Read a synthetic passage about a company and answer one specific "
        "fact-retrieval question. Deterministic; license-free."
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
        return f"synthetic-rag-v1-seed{self.seed}-n{self.n_instances}"

    def dataset_loader(self) -> Iterable[Example]:
        rng = random.Random(self.seed)
        for i in range(self.n_instances):
            company = rng.choice(_COMPANIES)
            attrs = _generate_attributes(rng)
            sentences = [_TEMPLATES[k].format(company=company, value=v) for k, v in attrs.items()]
            rng.shuffle(sentences)
            passage = " ".join(sentences)
            target_attr = rng.choice(list(attrs.keys()))
            question = _QUESTIONS[target_attr].format(company=company)
            yield Example(
                instance_id=f"rag-{i:04d}",
                prompt_inputs={"passage": passage, "question": question},
                ground_truth=attrs[target_attr],
            )

    def validator(self, output: str, ground_truth: Any) -> ValidationResult:
        normalized = _normalize_answer(output)
        if not normalized:
            return ValidationResult(
                passed=False,
                score=0.0,
                failure_reason="output is empty after normalization",
                failure_modes=[FailureMode.SCHEMA_BREAK],
            )

        expected = _normalize_answer(str(ground_truth))
        if normalized.lower() == expected.lower():
            return ValidationResult(passed=True, score=1.0)

        return ValidationResult(
            passed=False,
            score=0.0,
            failure_reason="answer text did not match expected (case-insensitive normalized)",
            failure_modes=[FailureMode.CONFABULATION],
        )


def _normalize_answer(text: str) -> str:
    """Strip surrounding whitespace, quotes, and a trailing period.

    Conservative: does NOT strip parenthesized clarifications, language tags,
    or other prose. A model that wraps the answer in extra commentary fails;
    that is the procurement-relevant signal (instruction-following on output
    format).
    """
    s = text.strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1].strip()
    if s.endswith("."):
        s = s[:-1].strip()
    return s
