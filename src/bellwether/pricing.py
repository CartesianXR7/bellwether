"""Per-provider per-model token pricing.

Pricing is loaded once at run-start and frozen for the run per METHODOLOGY s2.6.
No provider exposes a public pricing API; the table is populated by hand from
each provider's pricing page (URL recorded per entry for audit trail).

PRICING_TABLE is intentionally empty in this scaffold. Entries land alongside
each ProviderAdapter in v0 (one entry per provider/model the bench targets).
Tests construct Pricing instances inline.
"""

from __future__ import annotations

from dataclasses import dataclass

PRICING_VERSION = "2026-05-05"


@dataclass(frozen=True)
class Pricing:
    """USD per million tokens. Match the format on each provider's pricing page.

    model_class categorizes the architectural lineage so the leaderboard does
    not silently compare reasoning models against non-reasoning ones (their
    output-token economics differ structurally). Values:
        'standard'  : conventional chat completion model
        'reasoning' : explicit thinking-budget model (o3, o4-mini,
                      DeepSeek R1, Sonar Reasoning, etc.)
        'search'    : retrieval-augmented (Perplexity Sonar variants)
    Methodology s2.7 (added v0.1.1 PATCH) describes how leaderboard ranking
    handles cross-class comparison.
    """

    provider: str
    model: str
    input_per_million_usd: float
    output_per_million_usd: float
    as_of: str
    source_url: str
    model_class: str = "standard"


PRICING_TABLE: dict[tuple[str, str], Pricing] = {
    # ============================================================
    # Verification status (as of as_of date below):
    #   anthropic/claude-sonnet-4-6  : VERIFIED 2026-05-05 against
    #     platform.claude.com/docs/en/docs/about-claude/pricing.
    #   google/gemini-2.5-flash-lite : VERIFIED 2026-05-05 against
    #     ai.google.dev/pricing.
    #   openai/gpt-4o                : VERIFIED 2026-05-05 against the
    #     LiteLLM community pricing catalog (the official openai.com pricing
    #     page is a JS-rendered SPA that blocks scraping). LiteLLM's catalog
    #     records gpt-4o, gpt-4o-2024-08-06, and gpt-4o-2024-11-20 all at
    #     $2.50/$10 per million; cross-references match.
    #     Source: github.com/BerriAI/litellm model_prices_and_context_window_backup.json
    # Wrong pricing => wrong effective_TCoT => the leaderboard misranks.
    # source_url + as_of fields are the audit trail per METHODOLOGY s2.6.
    # ============================================================
    # --- Anthropic ---
    ("anthropic", "claude-sonnet-4-6"): Pricing(
        provider="anthropic",
        model="claude-sonnet-4-6",
        input_per_million_usd=3.00,
        output_per_million_usd=15.00,
        as_of="2026-05-05",
        source_url="https://platform.claude.com/docs/en/docs/about-claude/pricing",
    ),
    ("anthropic", "claude-haiku-4-5"): Pricing(
        provider="anthropic",
        model="claude-haiku-4-5",
        input_per_million_usd=1.00,
        output_per_million_usd=5.00,
        as_of="2026-05-07",
        source_url="https://platform.claude.com/docs/en/docs/about-claude/pricing",
    ),
    ("anthropic", "claude-opus-4-7"): Pricing(
        provider="anthropic",
        model="claude-opus-4-7",
        input_per_million_usd=5.00,
        output_per_million_usd=25.00,
        as_of="2026-05-07",
        source_url="https://platform.claude.com/docs/en/docs/about-claude/pricing",
    ),
    # --- OpenAI ---
    ("openai", "gpt-4o"): Pricing(
        provider="openai",
        model="gpt-4o",
        input_per_million_usd=2.50,
        output_per_million_usd=10.00,
        as_of="2026-05-05",
        source_url="https://openai.com/api/pricing/",
    ),
    ("openai", "gpt-4o-mini"): Pricing(
        provider="openai",
        model="gpt-4o-mini",
        input_per_million_usd=0.15,
        output_per_million_usd=0.60,
        as_of="2026-05-07",
        source_url="https://openai.com/api/pricing/",
    ),
    # --- Google ---
    ("google", "gemini-2.5-flash-lite"): Pricing(
        provider="google",
        model="gemini-2.5-flash-lite",
        input_per_million_usd=0.10,
        output_per_million_usd=0.40,
        as_of="2026-05-05",
        source_url="https://ai.google.dev/pricing",
    ),
    ("google", "gemini-2.5-flash"): Pricing(
        provider="google",
        model="gemini-2.5-flash",
        input_per_million_usd=0.30,
        output_per_million_usd=2.50,
        as_of="2026-05-07",
        source_url="https://ai.google.dev/pricing",
    ),
    ("google", "gemini-2.5-pro"): Pricing(
        provider="google",
        model="gemini-2.5-pro",
        input_per_million_usd=1.25,
        output_per_million_usd=10.00,
        as_of="2026-05-07",
        source_url="https://ai.google.dev/pricing",
    ),
    # --- xAI (Grok via OpenAI-compatible api.x.ai/v1) ---
    ("xai", "grok-4"): Pricing(
        provider="xai",
        model="grok-4",
        input_per_million_usd=3.00,
        output_per_million_usd=15.00,
        as_of="2026-05-08",
        source_url="https://docs.x.ai/docs/models",
    ),
    ("xai", "grok-4-fast"): Pricing(
        provider="xai",
        model="grok-4-fast",
        input_per_million_usd=0.20,
        output_per_million_usd=0.50,
        as_of="2026-05-08",
        source_url="https://docs.x.ai/docs/models",
    ),
    ("xai", "grok-3"): Pricing(
        provider="xai",
        model="grok-3",
        input_per_million_usd=3.00,
        output_per_million_usd=15.00,
        as_of="2026-05-08",
        source_url="https://docs.x.ai/docs/models",
    ),
    ("xai", "grok-3-mini"): Pricing(
        provider="xai",
        model="grok-3-mini",
        input_per_million_usd=0.30,
        output_per_million_usd=0.50,
        as_of="2026-05-08",
        source_url="https://docs.x.ai/docs/models",
    ),
    # --- Perplexity (Sonar via OpenAI-compatible api.perplexity.ai) ---
    # Token costs only here; per-search costs (~$5/1k searches) are not yet
    # captured. v0.5 adds search-cost accounting to TCoT for class=search.
    ("perplexity", "sonar"): Pricing(
        provider="perplexity",
        model="sonar",
        input_per_million_usd=1.00,
        output_per_million_usd=1.00,
        as_of="2026-05-08",
        source_url="https://docs.perplexity.ai/guides/pricing",
        model_class="search",
    ),
    ("perplexity", "sonar-pro"): Pricing(
        provider="perplexity",
        model="sonar-pro",
        input_per_million_usd=3.00,
        output_per_million_usd=15.00,
        as_of="2026-05-08",
        source_url="https://docs.perplexity.ai/guides/pricing",
        model_class="search",
    ),
    ("perplexity", "sonar-reasoning"): Pricing(
        provider="perplexity",
        model="sonar-reasoning",
        input_per_million_usd=1.00,
        output_per_million_usd=5.00,
        as_of="2026-05-08",
        source_url="https://docs.perplexity.ai/guides/pricing",
        model_class="reasoning",
    ),
    ("perplexity", "sonar-reasoning-pro"): Pricing(
        provider="perplexity",
        model="sonar-reasoning-pro",
        input_per_million_usd=2.00,
        output_per_million_usd=8.00,
        as_of="2026-05-08",
        source_url="https://docs.perplexity.ai/guides/pricing",
        model_class="reasoning",
    ),
    # --- OpenAI o-series (reasoning) ---
    ("openai", "o3"): Pricing(
        provider="openai",
        model="o3",
        input_per_million_usd=2.00,
        output_per_million_usd=8.00,
        as_of="2026-05-08",
        source_url="https://openai.com/api/pricing/",
        model_class="reasoning",
    ),
    ("openai", "o3-mini"): Pricing(
        provider="openai",
        model="o3-mini",
        input_per_million_usd=1.10,
        output_per_million_usd=4.40,
        as_of="2026-05-08",
        source_url="https://openai.com/api/pricing/",
        model_class="reasoning",
    ),
    ("openai", "o4-mini"): Pricing(
        provider="openai",
        model="o4-mini",
        input_per_million_usd=1.10,
        output_per_million_usd=4.40,
        as_of="2026-05-08",
        source_url="https://openai.com/api/pricing/",
        model_class="reasoning",
    ),
    # --- OpenRouter (open-weights + commercial via openrouter.ai/api/v1) ---
    # OpenRouter pricing typically mirrors upstream + small markup.
    ("openrouter", "meta-llama/llama-4-maverick"): Pricing(
        provider="openrouter",
        model="meta-llama/llama-4-maverick",
        input_per_million_usd=0.18,
        output_per_million_usd=0.59,
        as_of="2026-05-08",
        source_url="https://openrouter.ai/models",
    ),
    ("openrouter", "meta-llama/llama-4-scout"): Pricing(
        provider="openrouter",
        model="meta-llama/llama-4-scout",
        input_per_million_usd=0.10,
        output_per_million_usd=0.30,
        as_of="2026-05-08",
        source_url="https://openrouter.ai/models",
    ),
    ("openrouter", "meta-llama/llama-3.3-70b-instruct"): Pricing(
        provider="openrouter",
        model="meta-llama/llama-3.3-70b-instruct",
        input_per_million_usd=0.39,
        output_per_million_usd=0.39,
        as_of="2026-05-08",
        source_url="https://openrouter.ai/models",
    ),
    ("openrouter", "deepseek/deepseek-chat"): Pricing(
        provider="openrouter",
        model="deepseek/deepseek-chat",
        input_per_million_usd=0.28,
        output_per_million_usd=1.10,
        as_of="2026-05-08",
        source_url="https://openrouter.ai/models",
    ),
    ("openrouter", "deepseek/deepseek-r1"): Pricing(
        provider="openrouter",
        model="deepseek/deepseek-r1",
        input_per_million_usd=0.55,
        output_per_million_usd=2.19,
        as_of="2026-05-08",
        source_url="https://openrouter.ai/models",
        model_class="reasoning",
    ),
    ("openrouter", "mistralai/mistral-large"): Pricing(
        provider="openrouter",
        model="mistralai/mistral-large",
        input_per_million_usd=2.00,
        output_per_million_usd=6.00,
        as_of="2026-05-08",
        source_url="https://openrouter.ai/models",
    ),
    ("openrouter", "cohere/command-r-plus"): Pricing(
        provider="openrouter",
        model="cohere/command-r-plus",
        input_per_million_usd=2.50,
        output_per_million_usd=10.00,
        as_of="2026-05-08",
        source_url="https://openrouter.ai/models",
    ),
    ("openrouter", "qwen/qwen-3-235b-a22b"): Pricing(
        provider="openrouter",
        model="qwen/qwen-3-235b-a22b",
        input_per_million_usd=0.50,
        output_per_million_usd=0.50,
        as_of="2026-05-08",
        source_url="https://openrouter.ai/models",
    ),
}


def cost_for(pricing: Pricing, input_tokens: int, output_tokens: int) -> float:
    """Compute USD cost for one attempt's token counts at the given pricing."""
    return (
        input_tokens / 1_000_000 * pricing.input_per_million_usd
        + output_tokens / 1_000_000 * pricing.output_per_million_usd
    )


def lookup(provider: str, model: str) -> Pricing:
    """Look up Pricing for (provider, model). Raises KeyError if unknown.

    The error message points at the table entry that needs to be added; this
    is the surface that catches "we wired up an adapter but forgot to record
    pricing" before a benchmark run silently records cost=0.
    """
    key = (provider, model)
    if key not in PRICING_TABLE:
        raise KeyError(
            f"No pricing entry for ({provider!r}, {model!r}). "
            f"Add it to PRICING_TABLE in bellwether/pricing.py with verified "
            f"values from the provider's pricing page."
        )
    return PRICING_TABLE[key]
