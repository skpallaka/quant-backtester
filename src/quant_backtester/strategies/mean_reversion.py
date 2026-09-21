from __future__ import annotations

import pandas as pd

from quant_backtester.engine.strategy import Strategy


class MeanReversionStrategy(Strategy):
    """Bets that price snaps back toward its rolling mean.

    Computes a z-score of the current close against a rolling window's
    mean/std. Far below the mean (z < -threshold) -> buy, expecting reversion
    up. Far above (z > threshold) -> exit/short, expecting reversion down.
    """

    def __init__(self, window: int = 20, z_threshold: float = 1.0, allow_short: bool = False):
        self.window = window
        self.z_threshold = z_threshold
        self.allow_short = allow_short
        self.warmup_period = window

    def generate_signal(self, history: pd.DataFrame) -> float:
        close = history["close"].tail(self.window)
        mean = close.mean()
        std = close.std(ddof=1)
        if std == 0 or pd.isna(std):
            return 0.0

        z = (close.iloc[-1] - mean) / std
        if z < -self.z_threshold:
            return 1.0
        if z > self.z_threshold:
            return -1.0 if self.allow_short else 0.0
        return 0.0
