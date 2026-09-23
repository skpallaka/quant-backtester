"""Backtest every strategy across a diversified ticker universe and report
aggregate statistics.

The question this answers: is an edge found on one ticker (e.g. logistic
regression on QQQ) real signal, or a ticker-specific fluke? Tickers are
grouped into categories -- index/ETF, mega-cap tech, non-tech large-cap --
so results can be sliced to see whether a strategy generalizes across
sectors or only "works" on trending mega-cap names.

Run with: python scripts/run_backtest_grid.py
"""

from __future__ import annotations

import pandas as pd

from quant_backtester.data.loader import fetch_ohlcv
from quant_backtester.engine.backtest import BacktestEngine
from quant_backtester.engine.validation import time_based_split
from quant_backtester.metrics.metrics import bootstrap_confidence_interval, max_drawdown, sharpe_ratio
from quant_backtester.strategies.logistic import LogisticRegressionStrategy
from quant_backtester.strategies.mean_reversion import MeanReversionStrategy
from quant_backtester.strategies.momentum import MomentumStrategy
from quant_backtester.strategies.moving_average import MovingAverageCrossover
from quant_backtester.strategies.rsi import RSIStrategy

TICKERS = {
    "SPY": "index_etf",
    "QQQ": "index_etf",
    "IWM": "index_etf",
    "TLT": "index_etf",
    "AAPL": "mega_cap_tech",
    "MSFT": "mega_cap_tech",
    "NVDA": "mega_cap_tech",
    "GOOGL": "mega_cap_tech",
    "JPM": "non_tech_large_cap",
    "XOM": "non_tech_large_cap",
    "JNJ": "non_tech_large_cap",
}

START, END = "2018-01-01", "2024-01-01"


def build_strategies(train: pd.DataFrame) -> dict:
    logistic = LogisticRegressionStrategy()
    logistic.fit(train)
    return {
        "moving_average_crossover": MovingAverageCrossover(short_window=10, long_window=50),
        "rsi": RSIStrategy(period=14),
        "momentum": MomentumStrategy(lookback=20),
        "mean_reversion": MeanReversionStrategy(window=20, z_threshold=1.0),
        "logistic_regression": logistic,
    }


def run_one_ticker(ticker: str) -> list[dict]:
    data = fetch_ohlcv(ticker, START, END)
    train, test = time_based_split(data, test_size=0.2)
    strategies = build_strategies(train)

    rows = []
    for name, strategy in strategies.items():
        result = BacktestEngine(test, strategy, cost_bps=5.0).run()
        ci = bootstrap_confidence_interval(result.returns.to_numpy(), n_resamples=1000, random_state=7)
        rows.append({
            "ticker": ticker,
            "category": TICKERS[ticker],
            "strategy": name,
            "total_return": result.equity_curve.iloc[-1] / result.equity_curve.iloc[0] - 1,
            "sharpe": sharpe_ratio(result.returns),
            "max_dd": max_drawdown(result.equity_curve),
            "ci_lower": ci["lower"],
            "ci_upper": ci["upper"],
            "significant_positive": ci["lower"] > 0,
        })
    return rows


def main() -> None:
    all_rows: list[dict] = []
    for ticker, category in TICKERS.items():
        print(f"Running {ticker} ({category})...")
        try:
            all_rows.extend(run_one_ticker(ticker))
        except Exception as exc:
            print(f"  skipped {ticker}: {exc}")

    df = pd.DataFrame(all_rows)
    pd.set_option("display.width", 160)
    pd.set_option("display.max_rows", None)

    print("\n=== Per ticker x strategy ===")
    print(df.sort_values(["strategy", "category", "ticker"]).to_string(index=False))

    print("\n=== Aggregate by strategy (across all tickers) ===")
    agg = df.groupby("strategy").agg(
        avg_sharpe=("sharpe", "mean"),
        min_sharpe=("sharpe", "min"),
        max_sharpe=("sharpe", "max"),
        pct_significant_positive=("significant_positive", "mean"),
    ).sort_values("avg_sharpe", ascending=False)
    print(agg.to_string())

    print("\n=== Aggregate by strategy x category (avg Sharpe) ===")
    agg2 = df.groupby(["strategy", "category"])["sharpe"].mean().unstack()
    print(agg2.to_string())

    out_path = "backtest_grid_results.csv"
    df.to_csv(out_path, index=False)
    print(f"\nSaved full results to {out_path}")


if __name__ == "__main__":
    main()
