"""
risk.py
-------
Capital allocation strategy: how much notional to risk per opportunity,
and when to stop trading entirely.

Two mechanisms, both standard in a real strategy's risk book:

1. Volatility-scaled position sizing. Position size shrinks as realized
   volatility rises, since (a) slippage risk is higher and (b) the latency
   decay in latency_cost_model.py means edges are less reliable when prices
   are moving fast.

2. A drawdown circuit breaker. If cumulative session losses exceed a
   threshold fraction of allocated capital, trading halts for the rest of
   the session. This is what "risk parameters during extreme market
   volatility" concretely means: a hard stop, not a hope.
"""

from dataclasses import dataclass, field

from market_feed import VolatilityRegime


@dataclass
class RiskParameters:
    total_capital_usd: float
    base_risk_fraction: float = 0.02       # fraction of capital risked per normal-regime trade
    max_daily_drawdown_fraction: float = 0.06   # halt trading if session P&L drops this far
    vol_scale: dict = field(default_factory=lambda: {
        VolatilityRegime.CALM: 1.25,
        VolatilityRegime.NORMAL: 1.0,
        VolatilityRegime.EXTREME: 0.25,   # cut size sharply in extreme regime
    })


class RiskManager:
    def __init__(self, params: RiskParameters):
        self.params = params
        self.session_pnl = 0.0
        self.halted = False
        self.halt_reason = None

    def position_size_usd(self, regime: VolatilityRegime) -> float:
        if self.halted:
            return 0.0
        scale = self.params.vol_scale.get(regime, 1.0)
        return self.params.total_capital_usd * self.params.base_risk_fraction * scale

    def record_fill(self, pnl_usd: float):
        self.session_pnl += pnl_usd
        drawdown_limit = -self.params.total_capital_usd * self.params.max_daily_drawdown_fraction
        if self.session_pnl <= drawdown_limit and not self.halted:
            self.halted = True
            self.halt_reason = (
                f"Session drawdown {self.session_pnl:,.2f} breached limit "
                f"{drawdown_limit:,.2f} ({self.params.max_daily_drawdown_fraction:.0%} of capital)"
            )

    def status(self) -> dict:
        return {
            "session_pnl_usd": round(self.session_pnl, 2),
            "halted": self.halted,
            "halt_reason": self.halt_reason,
        }
