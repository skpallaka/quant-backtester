"""The core backtest loop.

Lookahead-bias prevention, explained:
  On bar t, the strategy is shown `data.iloc[:t+1]` -- every row up to and
  including bar t's close, nothing more. Its signal is then executed at
  bar t+1's OPEN, one step after the strategy ever saw it. So a signal
  computed from information available "as of the close of day t" is filled
  at a price the strategy never had access to when it decided. There is no
  path in this loop for a strategy to trade on a price before it was set.

The engine itself knows nothing about *how* a strategy decides -- it only
calls `strategy.generate_signal(history)` and enforces the timing above.
That separation (engine vs. strategy) is the entire point of the
Strategy ABC in strategy.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from quant_backtester.engine.strategy import Strategy


@dataclass
class Trade:
    date: pd.Timestamp
    price: float
    shares_delta: float
    cost: float


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    returns: pd.Series
    trades: list[Trade] = field(default_factory=list)
    positions: pd.Series = field(default_factory=pd.Series)


class BacktestEngine:
    """Walks `data` day by day, asks `strategy` for a target position, and
    fills that target at the next bar's open, tracking cash/shares/equity.
    """

    def __init__(
        self,
        data: pd.DataFrame,
        strategy: Strategy,
        initial_cash: float = 100_000.0,
        cost_bps: float = 5.0,
        allow_short: bool = False,
    ):
        required_cols = {"open", "high", "low", "close", "volume"}
        missing = required_cols - set(data.columns)
        if missing:
            raise ValueError(f"data is missing required columns: {missing}")
        if not data.index.is_monotonic_increasing:
            raise ValueError("data must be sorted ascending by date")

        self.data = data
        self.strategy = strategy
        self.initial_cash = initial_cash
        self.cost_bps = cost_bps
        self.allow_short = allow_short

    def _execute_rebalance(self, cash: float, shares: float, target_position: float, price: float):
        target_position = float(np.clip(target_position, -1.0 if self.allow_short else 0.0, 1.0))
        portfolio_value = cash + shares * price
        desired_shares = (target_position * portfolio_value) / price if price > 0 else shares
        delta_shares = desired_shares - shares

        trade = None
        if abs(delta_shares) > 1e-9:
            trade_value = abs(delta_shares) * price
            cost = trade_value * (self.cost_bps / 10_000.0)
            cash -= delta_shares * price + cost
            shares = desired_shares
            trade = (delta_shares, cost)

        return cash, shares, trade

    def run(self) -> BacktestResult:
        self.strategy.reset()

        n = len(self.data)
        dates = self.data.index
        opens = self.data["open"].to_numpy()
        closes = self.data["close"].to_numpy()

        cash = self.initial_cash
        shares = 0.0
        pending_target: float | None = None

        equity = np.empty(n)
        position_frac = np.empty(n)
        trades: list[Trade] = []
        warmup = self.strategy.warmup_period

        for i in range(n):
            if pending_target is not None:
                cash, shares, trade = self._execute_rebalance(cash, shares, pending_target, opens[i])
                if trade is not None:
                    delta_shares, cost = trade
                    trades.append(Trade(date=dates[i], price=opens[i], shares_delta=delta_shares, cost=cost))
                pending_target = None

            if i >= warmup:
                history = self.data.iloc[: i + 1]
                pending_target = self.strategy.generate_signal(history)

            portfolio_value = cash + shares * closes[i]
            equity[i] = portfolio_value
            position_frac[i] = (shares * closes[i]) / portfolio_value if portfolio_value != 0 else 0.0

        equity_curve = pd.Series(equity, index=dates, name="equity")
        returns = equity_curve.pct_change().fillna(0.0)
        positions = pd.Series(position_frac, index=dates, name="position")

        return BacktestResult(equity_curve=equity_curve, returns=returns, trades=trades, positions=positions)
