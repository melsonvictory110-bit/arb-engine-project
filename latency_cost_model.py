"""
latency_cost_model.py
----------------------
The business challenge: does colocation infrastructure pay for itself?

An arbitrage opportunity decays the moment it's visible, because everyone
polling the same venues can see it. Higher latency between quote-generation
and order-arrival means a larger fraction of opportunities either shrink
below the profitable threshold or vanish (get filled by someone faster)
before your order lands. This module quantifies that decay and weighs it
against the fixed cost of buying lower latency.
"""

from dataclasses import dataclass


@dataclass
class InfraTier:
    name: str
    network_latency_ms: float      # one-way-ish effective latency to venue
    jitter_ms: float
    monthly_cost_usd: float


# Three representative tiers a student could realistically cost out.
RETAIL_CLOUD = InfraTier("Retail cloud VM (shared region)", network_latency_ms=120, jitter_ms=35, monthly_cost_usd=50)
PREMIUM_VPS = InfraTier("Premium VPS (same metro)", network_latency_ms=25, jitter_ms=8, monthly_cost_usd=400)
COLOCATION = InfraTier("Colocation, cross-connect to exchange", network_latency_ms=1.2, jitter_ms=0.3, monthly_cost_usd=6500)


def opportunity_survival_probability(latency_ms: float, decay_halflife_ms: float = 180.0) -> float:
    """
    Models the probability that a detected arbitrage window is still
    capturable after `latency_ms` of round-trip delay. Real arb windows on
    liquid crypto pairs typically close in the low hundreds of ms as other
    participants react; this uses an exponential decay as a defensible
    first-order approximation for a feasibility study (not a production
    market-microstructure model).
    """
    import math
    return math.exp(-math.log(2) * latency_ms / decay_halflife_ms)


def expected_captured_profit(gross_edge_bps: float, notional_usd: float,
                              latency_ms: float, decay_halflife_ms: float = 180.0) -> float:
    """Expected $ profit per opportunity, after latency decay, before fees."""
    survival = opportunity_survival_probability(latency_ms, decay_halflife_ms)
    return (gross_edge_bps / 10_000) * notional_usd * survival


def breakeven_analysis(tier: InfraTier, retail_tier: InfraTier, gross_edge_bps: float,
                        notional_usd: float, opportunities_per_day: float,
                        decay_halflife_ms: float = 180.0) -> dict:
    """
    Compares `tier` against a `retail_tier` baseline and asks: how many
    trading days does it take for the *incremental* profit captured by the
    faster tier to pay for its *incremental* monthly cost?
    """
    fast_profit = expected_captured_profit(gross_edge_bps, notional_usd, tier.network_latency_ms, decay_halflife_ms)
    base_profit = expected_captured_profit(gross_edge_bps, notional_usd, retail_tier.network_latency_ms, decay_halflife_ms)

    incremental_profit_per_opportunity = fast_profit - base_profit
    incremental_daily_profit = incremental_profit_per_opportunity * opportunities_per_day
    incremental_monthly_cost = tier.monthly_cost_usd - retail_tier.monthly_cost_usd

    if incremental_daily_profit <= 0:
        payback_days = float("inf")
    else:
        payback_days = incremental_monthly_cost / incremental_daily_profit

    return {
        "tier": tier.name,
        "incremental_monthly_cost_usd": round(incremental_monthly_cost, 2),
        "incremental_daily_profit_usd": round(incremental_daily_profit, 2),
        "payback_days": round(payback_days, 1) if payback_days != float("inf") else None,
        "worth_it_within_30d": (payback_days <= 30) if payback_days != float("inf") else False,
    }


if __name__ == "__main__":
    # quick standalone sanity check
    for tier in (PREMIUM_VPS, COLOCATION):
        result = breakeven_analysis(
            tier=tier,
            retail_tier=RETAIL_CLOUD,
            gross_edge_bps=8.0,
            notional_usd=25_000,
            opportunities_per_day=40,
        )
        print(result)
