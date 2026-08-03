"""
engine.py
---------
Trade-execution logic. Consumes quotes from two concurrent ExchangeFeed
pollers, computes the net spread after modeled fees and latency decay,
and decides whether to execute — sizing the trade via RiskManager.

This is deliberately a *simulation*: no real order is sent anywhere. The
purpose is to demonstrate the decision pipeline (detect -> cost-adjust ->
size -> execute/skip -> record) under realistic concurrency and latency
constraints, which is what the assignment's technical focus asks for.
"""

import asyncio
import random
import time
from dataclasses import dataclass, field

from market_feed import ExchangeFeed, Quote, VolatilityRegime
from latency_cost_model import opportunity_survival_probability, InfraTier
from risk import RiskManager


TAKER_FEE_BPS_PER_LEG = 5.0  # typical taker fee; paid on both legs of the arb


@dataclass
class ExecutionEvent:
    ts: float
    action: str            # "FILL" or "SKIP"
    gross_edge_bps: float
    net_edge_bps: float
    notional_usd: float
    pnl_usd: float
    reason: str = ""


@dataclass
class SessionResult:
    events: list = field(default_factory=list)
    fills: int = 0
    skips: int = 0
    gross_pnl_usd: float = 0.0

    def summary(self) -> dict:
        return {
            "fills": self.fills,
            "skips": self.skips,
            "fill_rate": round(self.fills / max(1, self.fills + self.skips), 3),
            "gross_pnl_usd": round(self.gross_pnl_usd, 2),
        }


async def run_session(
    infra_tier: InfraTier,
    regime: VolatilityRegime,
    risk_manager: RiskManager,
    duration_s: float = 20.0,
    poll_interval_s: float = 0.25,
    start_price: float = 50_000.0,
) -> SessionResult:
    """
    Runs the concurrency pipeline for `duration_s` seconds of simulated time
    and returns a SessionResult log. Two ExchangeFeed pollers run as
    independent asyncio tasks, both writing into a shared queue; a third
    task (this coroutine's main loop) consumes quotes and evaluates trades.
    """
    queue: asyncio.Queue = asyncio.Queue()
    stop_event = asyncio.Event()

    feed_a = ExchangeFeed("Exchange A", start_price, base_spread_bps=2.0,
                           poll_interval_s=poll_interval_s, regime=regime)
    feed_b = ExchangeFeed("Exchange B", start_price * 1.0007, base_spread_bps=2.0,
                           poll_interval_s=poll_interval_s, regime=regime)

    latency_s = infra_tier.network_latency_ms / 1000
    jitter_s = infra_tier.jitter_ms / 1000

    task_a = asyncio.create_task(feed_a.poll(queue, latency_s, jitter_s, stop_event))
    task_b = asyncio.create_task(feed_b.poll(queue, latency_s, jitter_s, stop_event))

    latest: dict[str, Quote] = {}
    result = SessionResult()
    session_start = time.monotonic()

    while time.monotonic() - session_start < duration_s:
        try:
            quote = await asyncio.wait_for(queue.get(), timeout=0.5)
        except asyncio.TimeoutError:
            continue
        latest[quote.exchange] = quote

        if "Exchange A" not in latest or "Exchange B" not in latest:
            continue

        qa, qb = latest["Exchange A"], latest["Exchange B"]
        # try both directions: buy low venue, sell high venue
        directions = [
            (qa.ask, qb.bid, "buy A / sell B"),
            (qb.ask, qa.bid, "buy B / sell A"),
        ]
        buy_px, sell_px, direction = max(directions, key=lambda d: d[1] - d[0])

        gross_edge_bps = ((sell_px - buy_px) / buy_px) * 10_000
        net_edge_bps = gross_edge_bps - (2 * TAKER_FEE_BPS_PER_LEG)

        # latency decay: how much of this opportunity survives round-trip delay
        survival = opportunity_survival_probability(infra_tier.network_latency_ms)
        realized_edge_bps = net_edge_bps * survival

        notional = risk_manager.position_size_usd(regime)

        if realized_edge_bps > 0 and notional > 0:
            pnl = (realized_edge_bps / 10_000) * notional
            # extreme-vol slippage haircut on fills
            if regime is VolatilityRegime.EXTREME:
                pnl *= random.uniform(0.4, 0.9)
            risk_manager.record_fill(pnl)
            result.fills += 1
            result.gross_pnl_usd += pnl
            result.events.append(ExecutionEvent(
                ts=time.monotonic(), action="FILL",
                gross_edge_bps=round(gross_edge_bps, 2), net_edge_bps=round(realized_edge_bps, 2),
                notional_usd=round(notional, 2), pnl_usd=round(pnl, 2), reason=direction,
            ))
        else:
            result.skips += 1
            reason = "risk halted" if risk_manager.halted else "edge below cost threshold after latency decay"
            result.events.append(ExecutionEvent(
                ts=time.monotonic(), action="SKIP",
                gross_edge_bps=round(gross_edge_bps, 2), net_edge_bps=round(realized_edge_bps, 2),
                notional_usd=0.0, pnl_usd=0.0, reason=reason,
            ))

    stop_event.set()
    for t in (task_a, task_b):
        t.cancel()
    return result
    
