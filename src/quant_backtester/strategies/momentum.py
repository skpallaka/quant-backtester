from __future__ import annotations

import pandas as pd

from quant_backtester.engine.strategy import Strategy


class MomentumStrategy(Strategy):
    """Long if price is higher than `lookback` bars ago, else flat/short.

    Bets that recent trends persist: an asset that has been rising is more
    likely to keep rising than one picked at random (and vice versa).
    """

    def __init__(self, lookback: int = 20, allow_short: bool = False):
        self.lookback = lookback
        self.allow_short = allow_short
        self.warmup_period = lookback + 1

    def generate_signal(self, history: pd.DataFrame) -> float:
        close = history["close"]
        past_price = close.iloc[-(self.lookback + 1)]
        current_price = close.iloc[-1]

        if current_price > past_price:
            return 1.0
        return -1.0 if self.allow_short else 0.0
