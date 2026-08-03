"""
market_feed.py
--------------
Simulates two exchange order books being polled concurrently via asyncio.
This is the "concurrency pipeline" layer: two independent async tasks
generate ticking bid/ask quotes, standing in for real REST/WebSocket polling
against two venues (e.g. Exchange A / Exchange B for the same instrument).

In a production system, `poll_exchange` would be replaced with real HTTP/WS
calls. The interface (async generator yielding Quote objects) is designed so
that swap is mechanical.
"""

import asyncio
import random
import time
from dataclasses import dataclass
from enum import Enum


class VolatilityRegime(Enum):
    CALM = "calm"
    NORMAL = "normal"
    EXTREME = "extreme"

    @property
    def tick_stddev(self) -> float:
        """Per-tick price move, in absolute price units, for a ~$50k asset."""
        return {"calm": 1.5, "normal": 6.0, "extreme": 28.0}[self.value]

    @property
    def spread_widen_factor(self) -> float:
        """How much wider bid/ask spreads get under this regime."""
        return {"calm": 1.0, "normal": 1.4, "extreme": 3.2}[self.value]


@dataclass
class Quote:
    exchange: str
    bid: float
    ask: float
    ts_monotonic: float  # time.monotonic() at generation, for latency math


class ExchangeFeed:
    """
    One simulated exchange. Produces a random-walk mid price and derives
    bid/ask from a base spread that widens under volatility.
    """

    def __init__(self, name: str, start_price: float, base_spread_bps: float,
                 poll_interval_s: float, regime: VolatilityRegime):
        self.name = name
        self.mid = start_price
        self.base_spread_bps = base_spread_bps
        self.poll_interval_s = poll_interval_s
        self.regime = regime

    def _step(self) -> Quote:
        self.mid += random.gauss(0, self.regime.tick_stddev)
        half_spread = self.mid * (self.base_spread_bps / 10_000) * self.regime.spread_widen_factor / 2
        return Quote(
            exchange=self.name,
            bid=round(self.mid - half_spread, 2),
            ask=round(self.mid + half_spread, 2),
            ts_monotonic=time.monotonic(),
        )

    async def poll(self, out_queue: asyncio.Queue, network_latency_s: float,
                    jitter_s: float, stop_event: asyncio.Event):
        """
        Continuously polls this exchange. `network_latency_s` models the
        round-trip cost of reaching the venue (colocated vs retail internet);
        `jitter_s` adds per-poll variance, since real networks are not
        constant-latency.
        """
        while not stop_event.is_set():
            quote = self._step()
            # simulate the network round trip before the quote "arrives"
            delay = max(0.0, network_latency_s + random.gauss(0, jitter_s))
            await asyncio.sleep(delay)
            await out_queue.put(quote)
            await asyncio.sleep(self.poll_interval_s)
