"""End-to-end example: fetch data, time-split it, backtest every strategy on
the held-out test period, and report Sharpe / max drawdown / bootstrap CI.

Run with:  python scripts/run_backtest.py [TICKER]
"""

from __future__ import annotations

import sys

from quant_backtester.data.loader import fetch_ohlcv
from quant_backtester.engine.backtest import BacktestEngine
from quant_backtester.engine.validation import time_based_split
from quant_backtester.metrics.metrics import bootstrap_confidence_interval, max_drawdown, sharpe_ratio
from quant_backtester.strategies.logistic import LogisticRegressionStrategy
from quant_backtester.strategies.mean_reversion import MeanReversionStrategy
from quant_backtester.strategies.momentum import MomentumStrategy
from quant_backtester.strategies.moving_average import MovingAverageCrossover
from quant_backtester.strategies.rsi import RSIStrategy


def report(name: str, returns, equity_curve) -> None:
    sharpe = sharpe_ratio(returns)
    mdd = max_drawdown(equity_curve)
    ci = bootstrap_confidence_interval(returns.to_numpy(), metric_fn=lambda r: r.mean(), n_resamples=1000, random_state=7)
    total_return = equity_curve.iloc[-1] / equity_curve.iloc[0] - 1

    print(f"{name:28s} total_return={total_return:+7.2%}  sharpe={sharpe:6.2f}  "
          f"max_dd={mdd:7.2%}  mean_ret_95%CI=[{ci['lower']:+.5f}, {ci['upper']:+.5f}]")


def main() -> None:
    ticker = sys.argv[1] if len(sys.argv) > 1 else "SPY"
    print(f"Fetching {ticker}...")
    data = fetch_ohlcv(ticker, "2018-01-01", "2024-01-01")
    print(f"Loaded {len(data)} bars: {data.index.min().date()} -> {data.index.max().date()}\n")

    train, test = time_based_split(data, test_size=0.2)
    print(f"Train: {len(train)} bars ({train.index.min().date()} -> {train.index.max().date()})")
    print(f"Test:  {len(test)} bars ({test.index.min().date()} -> {test.index.max().date()})\n")

    logistic = LogisticRegressionStrategy()
    logistic.fit(train)

    strategies = {
        "buy_and_hold_MA_crossover": MovingAverageCrossover(short_window=10, long_window=50),
        "RSI(14)": RSIStrategy(period=14),
        "momentum(20)": MomentumStrategy(lookback=20),
        "mean_reversion(20,1.0)": MeanReversionStrategy(window=20, z_threshold=1.0),
        "logistic_regression": logistic,
    }

    print("Results on held-out test period (no lookahead: trained on train only, walked forward on test):")
    for name, strategy in strategies.items():
        result = BacktestEngine(test, strategy, cost_bps=5.0).run()
        report(name, result.returns, result.equity_curve)


if __name__ == "__main__":
    main()
