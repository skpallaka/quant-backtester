from __future__ import annotations

import pandas as pd

from quant_backtester.engine.strategy import Strategy


def _rsi(close: pd.Series, period: int) -> float:
    """Wilder's RSI over the last `period` bars of `close`. Returns the most recent value."""
    delta = close.diff().dropna()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)

    avg_gain = gains.tail(period).mean()
    avg_loss = losses.tail(period).mean()

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


class RSIStrategy(Strategy):
    """Mean-reversion on RSI: buy when oversold, exit/short when overbought.

    RSI measures the ratio of recent up-moves to down-moves. Below
    `oversold` means selling has been disproportionate -- a bounce is
    favored. Above `overbought` means the same in reverse.
    """

    def __init__(self, period: int = 14, oversold: float = 30.0, overbought: float = 70.0, allow_short: bool = False):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self.allow_short = allow_short
        self.warmup_period = period + 1

    def generate_signal(self, history: pd.DataFrame) -> float:
        rsi = _rsi(history["close"], self.period)

        if rsi < self.oversold:
            return 1.0
        if rsi > self.overbought:
            return -1.0 if self.allow_short else 0.0
        return 0.0
