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
    """USD per million tokens. Match the format on each provider's pricing page."""

    provider: str
    model: str
    input_per_million_usd: float
    output_per_million_usd: float
    as_of: str
    source_url: str


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
    ("anthropic", "claude-sonnet-4-6"): Pricing(
        provider="anthropic",
        model="claude-sonnet-4-6",
        input_per_million_usd=3.00,
        output_per_million_usd=15.00,
        as_of="2026-05-05",
        source_url="https://platform.claude.com/docs/en/docs/about-claude/pricing",
    ),
    ("openai", "gpt-4o"): Pricing(
        provider="openai",
        model="gpt-4o",
        input_per_million_usd=2.50,
        output_per_million_usd=10.00,
        as_of="2026-05-05",
        source_url="https://openai.com/api/pricing/",
    ),
    ("google", "gemini-2.5-flash-lite"): Pricing(
        provider="google",
        model="gemini-2.5-flash-lite",
        input_per_million_usd=0.10,
        output_per_million_usd=0.40,
        as_of="2026-05-05",
        source_url="https://ai.google.dev/pricing",
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
