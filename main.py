import asyncio
import time
from dataclasses import dataclass

@dataclass
class OrderBook:
    venue: str
    best_bid: float
    best_ask: float

class ArbitrageEngine:
    def __init__(self, min_profit_bps: float = 5.0, taker_fee_bps: float = 1.5):
        self.min_profit_margin = min_profit_bps / 10000.0
        self.total_fee_margin = (2 * taker_fee_bps) / 10000.0

    def evaluate_spread(self, book_a: OrderBook, book_b: OrderBook):
        # Direction 1: Buy A -> Sell B
        spread_1 = (book_b.best_bid - book_a.best_ask) / book_a.best_ask
        net_yield_1 = spread_1 - self.total_fee_margin

        # Direction 2: Buy B -> Sell A
        spread_2 = (book_a.best_bid - book_b.best_ask) / book_b.best_ask
        net_yield_2 = spread_2 - self.total_fee_margin

        if net_yield_1 > self.min_profit_margin:
            return "BUY_A_SELL_B", net_yield_1 * 10000.0
        elif net_yield_2 > self.min_profit_margin:
            return "BUY_B_SELL_A", net_yield_2 * 10000.0
        
        return "NO_TRADE", max(net_yield_1, net_yield_2) * 10000.0