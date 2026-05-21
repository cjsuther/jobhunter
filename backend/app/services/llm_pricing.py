"""Pricing table for Anthropic models + cost computation helpers.

Prices are USD per million tokens. Update when Anthropic changes pricing.
Source: https://www.anthropic.com/pricing (as of 2026-05).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPricing:
    input: float  # per MTok, regular input
    output: float  # per MTok, output
    cache_write: float  # per MTok, tokens written to ephemeral cache
    cache_read: float  # per MTok, tokens served from cache (cheap)


# Pricing per million tokens (USD). Keys match the model IDs we send to the SDK.
PRICING: dict[str, ModelPricing] = {
    "claude-haiku-4-5-20251001": ModelPricing(
        input=1.00, output=5.00, cache_write=1.25, cache_read=0.10
    ),
    "claude-haiku-4-5": ModelPricing(
        input=1.00, output=5.00, cache_write=1.25, cache_read=0.10
    ),
    "claude-sonnet-4-6": ModelPricing(
        input=3.00, output=15.00, cache_write=3.75, cache_read=0.30
    ),
    "claude-opus-4-7": ModelPricing(
        input=15.00, output=75.00, cache_write=18.75, cache_read=1.50
    ),
}


# Reasonable fallback when we hit an unknown model — use Sonnet pricing so we
# don't under-report.
FALLBACK = ModelPricing(input=3.00, output=15.00, cache_write=3.75, cache_read=0.30)


def compute_cost_usd(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
) -> float:
    """Return the USD cost of a single API call with these token counts."""
    p = PRICING.get(model, FALLBACK)
    cost = (
        input_tokens * p.input
        + output_tokens * p.output
        + cache_creation_input_tokens * p.cache_write
        + cache_read_input_tokens * p.cache_read
    ) / 1_000_000.0
    return round(cost, 6)
