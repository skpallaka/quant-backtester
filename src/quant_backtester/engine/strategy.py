"""Strategy interface.

A Strategy is anything that maps price history up to "today" onto a desired
position. The engine never gives a strategy anything beyond the current bar,
so a correct strategy cannot see the future by construction.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class Strategy(ABC):
    """Base class every strategy implements.

    `generate_signal` receives `history`, a DataFrame of OHLCV rows up to and
    including the current bar (row 0..t). It must return a target position
    in [-1, 1]: 1.0 = fully long, -1.0 = fully short, 0.0 = flat. Long-only
    strategies should clip to [0, 1].
    """

    #: Minimum number of bars of history required before a strategy will
    #: produce a real signal (rather than 0.0 / flat).
    warmup_period: int = 0

    @abstractmethod
    def generate_signal(self, history: pd.DataFrame) -> float:
        raise NotImplementedError

    def reset(self) -> None:
        """Override if a strategy holds mutable state across a run."""
        return None


class BuyAndHoldStrategy(Strategy):
    """Dummy strategy: always fully long. Used to validate the engine plumbing."""

    warmup_period = 0

    def generate_signal(self, history: pd.DataFrame) -> float:
        return 1.0
