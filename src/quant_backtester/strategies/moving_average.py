from __future__ import annotations

import pandas as pd

from quant_backtester.engine.strategy import Strategy


class MovingAverageCrossover(Strategy):
    """Long when the short-window MA is above the long-window MA, else flat/short.

    Classic trend-following signal: the short MA reacting faster to price
    means a cross above the long MA signals a new uptrend forming.
    """

    def __init__(self, short_window: int = 20, long_window: int = 50, allow_short: bool = False):
        if short_window >= long_window:
            raise ValueError("short_window must be < long_window")
        self.short_window = short_window
        self.long_window = long_window
        self.allow_short = allow_short
        self.warmup_period = long_window

    def generate_signal(self, history: pd.DataFrame) -> float:
        close = history["close"]
        short_ma = close.tail(self.short_window).mean()
        long_ma = close.tail(self.long_window).mean()

        if short_ma > long_ma:
            return 1.0
        return -1.0 if self.allow_short else 0.0
