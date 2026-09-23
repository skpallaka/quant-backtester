"""Maps a strategy name (as passed over the API) to its class.

Only strategies that need nothing but constructor params are registered
here -- LogisticRegressionStrategy needs a `.fit(train_data)` call with an
explicit train window first, which doesn't fit a single "run this
strategy" request, so it's excluded until the API grows a way to express
a training range separately from the backtest range.
"""

from __future__ import annotations

from quant_backtester.engine.strategy import Strategy
from quant_backtester.strategies.mean_reversion import MeanReversionStrategy
from quant_backtester.strategies.momentum import MomentumStrategy
from quant_backtester.strategies.moving_average import MovingAverageCrossover
from quant_backtester.strategies.rsi import RSIStrategy

_REGISTRY = {
    "moving_average_crossover": MovingAverageCrossover,
    "rsi": RSIStrategy,
    "momentum": MomentumStrategy,
    "mean_reversion": MeanReversionStrategy,
}


def available_strategies() -> list[str]:
    return sorted(_REGISTRY)


def build_strategy(name: str, params: dict) -> Strategy:
    if name not in _REGISTRY:
        raise ValueError(f"Unknown strategy '{name}'. Available: {available_strategies()}")
    try:
        return _REGISTRY[name](**params)
    except TypeError as exc:
        raise ValueError(f"Invalid strategy_params for '{name}': {exc}") from None
