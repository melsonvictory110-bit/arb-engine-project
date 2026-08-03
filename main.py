"""
main.py
-------
Runs the full feasibility study:
  1. For each infrastructure tier, simulate trading sessions across three
     volatility regimes with the risk-managed execution engine.
  2. Report trade-execution outcomes per tier/regime.
  3. Run the standalone latency/colocation cost-benefit analysis.
  4. Print a single verdict table a student could hand in as the
     "capital allocation strategy" deliverable.

Usage:
    python3 main.py
"""

import asyncio

from market_feed import VolatilityRegime
from latency_cost_model import RETAIL_CLOUD, PREMIUM_VPS, COLOCATION, breakeven_analysis
from risk import RiskParameters, RiskManager
from engine import run_session

TIERS = [RETAIL_CLOUD, PREMIUM_VPS, COLOCATION]
REGIMES = [VolatilityRegime.CALM, VolatilityRegime.NORMAL, VolatilityRegime.EXTREME]

SESSION_DURATION_S = 8.0     # simulated seconds per (tier, regime) run
CAPITAL_USD = 250_000


async def run_full_study():
    print("=" * 78)
    print("ALGORITHMIC HIGH-FREQUENCY ARBITRAGE FEASIBILITY ENGINE")
    print("=" * 78)

    print("\n--- 1. TRADE-EXECUTION SIMULATION (per infra tier / vol regime) ---\n")
    header = f"{'Infra Tier':<38}{'Regime':<10}{'Fills':>7}{'Skips':>7}{'Fill %':>9}{'Gross P&L':>14}{'Halted':>9}"
    print(header)
    print("-" * len(header))

    rows = []
    for tier in TIERS:
        for regime in REGIMES:
            risk_params = RiskParameters(total_capital_usd=CAPITAL_USD)
            risk_manager = RiskManager(risk_params)
            result = await run_session(
                infra_tier=tier, regime=regime, risk_manager=risk_manager,
                duration_s=SESSION_DURATION_S,
            )
            summary = result.summary()
            rows.append((tier, regime, summary, risk_manager.status()))
            print(f"{tier.name:<38}{regime.value:<10}{summary['fills']:>7}{summary['skips']:>7}"
                  f"{summary['fill_rate']*100:>8.1f}%{summary['gross_pnl_usd']:>13,.2f} "
                  f"{'YES' if risk_manager.status()['halted'] else 'no':>8}")

    print("\n--- 2. LATENCY / COLOCATION COST-BENEFIT ANALYSIS ---\n")
    print("Question: does paying for lower latency infrastructure pay for itself")
    print("within a normal trading month, given the arb opportunities available?\n")
    for tier in (PREMIUM_VPS, COLOCATION):
        cb = breakeven_analysis(
            tier=tier, retail_tier=RETAIL_CLOUD,
            gross_edge_bps=8.0, notional_usd=25_000, opportunities_per_day=40,
        )
        verdict = "JUSTIFIED" if cb["worth_it_within_30d"] else "NOT JUSTIFIED"
        print(f"  {cb['tier']}")
        print(f"    incremental cost:   ${cb['incremental_monthly_cost_usd']:,.2f}/mo")
        print(f"    incremental profit: ${cb['incremental_daily_profit_usd']:,.2f}/day")
        payback = f"{cb['payback_days']} days" if cb["payback_days"] is not None else "never (infra cost never recovered)"
        print(f"    payback period:     {payback}")
        print(f"    verdict:            {verdict} within a 30-day month\n")

    print("--- 3. CAPITAL ALLOCATION STRATEGY (risk parameters) ---\n")
    rp = RiskParameters(total_capital_usd=CAPITAL_USD)
    print(f"  Total session capital:        ${rp.total_capital_usd:,.0f}")
    print(f"  Base risk per trade (normal): {rp.base_risk_fraction:.1%} of capital "
          f"(${rp.total_capital_usd * rp.base_risk_fraction:,.0f})")
    print(f"  Position sizing under calm:   {rp.vol_scale[VolatilityRegime.CALM]:.2f}x base")
    print(f"  Position sizing under extreme:{rp.vol_scale[VolatilityRegime.EXTREME]:.2f}x base "
          f"(cut to reduce slippage/latency-decay exposure)")
    print(f"  Drawdown circuit breaker:     halt all trading at "
          f"{rp.max_daily_drawdown_fraction:.0%} session loss "
          f"(${rp.total_capital_usd * rp.max_daily_drawdown_fraction:,.0f})")

    print("\n" + "=" * 78)
    print("Note: all figures are simulated. This engine demonstrates the decision")
    print("pipeline and cost-benefit method, not a live-tradable strategy.")
    print("=" * 78)


if __name__ == "__main__":
    asyncio.run(run_full_study())
