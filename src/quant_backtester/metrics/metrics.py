"""Performance metrics.

Sharpe ratio: excess return per unit of volatility -- how much reward you
got for the risk you took, not just the raw return.

Max drawdown: the worst peak-to-trough decline in the equity curve -- the
deepest hole a strategy ever dug that you'd have had to sit through.

Bootstrap confidence interval: resample the return series with replacement
many times, recompute the metric each time, and look at the spread of
results. If the interval is wide or straddles zero, the point estimate
could easily be noise rather than a repeatable edge.
"""

from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd


def sharpe_ratio(returns: pd.Series | np.ndarray, risk_free: float = 0.0, periods_per_year: int = 252) -> float:
    """Annualized Sharpe ratio of a periodic return series.

    (mean(excess_return) / std(excess_return)) scaled by sqrt(periods_per_year).
    Returns 0.0 if volatility is zero (avoids a divide-by-zero on a flat series).
    """
    r = np.asarray(returns, dtype=float)
    if len(r) == 0:
        return 0.0

    period_rf = risk_free / periods_per_year
    excess = r - period_rf
    std = excess.std(ddof=1)
    if std == 0 or np.isnan(std):
        return 0.0
    return float(np.sqrt(periods_per_year) * excess.mean() / std)


def max_drawdown(equity_curve: pd.Series | np.ndarray) -> float:
    """Largest peak-to-trough decline as a negative fraction (e.g. -0.23 = -23%)."""
    equity = np.asarray(equity_curve, dtype=float)
    if len(equity) == 0:
        return 0.0

    running_peak = np.maximum.accumulate(equity)
    drawdown = (equity - running_peak) / running_peak
    return float(drawdown.min())


def bootstrap_confidence_interval(
    returns: pd.Series | np.ndarray,
    metric_fn: Callable[[np.ndarray], float] = lambda r: r.mean(),
    n_resamples: int = 1000,
    confidence: float = 0.95,
    random_state: int | None = None,
) -> dict:
    """Bootstrap CI for `metric_fn` applied to `returns`.

    Draws `n_resamples` samples of len(returns), each sampled with
    replacement from `returns`, applies `metric_fn` to each, and returns
    the percentile interval. This answers "if the true return-generating
    process is like my observed sample, how much would this metric vary by
    chance alone?" -- it does NOT tell you whether the strategy will work
    out-of-sample, only whether the in-sample result is statistically
    distinguishable from noise.
    """
    r = np.asarray(returns, dtype=float)
    if len(r) == 0:
        return {"point_estimate": 0.0, "lower": 0.0, "upper": 0.0, "resamples": np.array([])}

    rng = np.random.default_rng(random_state)
    n = len(r)
    resample_estimates = np.empty(n_resamples)
    for i in range(n_resamples):
        sample = rng.choice(r, size=n, replace=True)
        resample_estimates[i] = metric_fn(sample)

    alpha = 1 - confidence
    lower, upper = np.percentile(resample_estimates, [100 * alpha / 2, 100 * (1 - alpha / 2)])

    return {
        "point_estimate": float(metric_fn(r)),
        "lower": float(lower),
        "upper": float(upper),
        "resamples": resample_estimates,
    }
