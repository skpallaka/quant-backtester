"""Populate the Postgres ohlcv cache for the full ticker universe
(quant_backtester.tickers.TICKERS) so downstream scripts -- the strategy
backtest grid, the Spark aggregation job -- can read from Postgres instead
of hitting yfinance themselves.

Run with: python scripts/fetch_universe.py
"""

from __future__ import annotations

from quant_backtester.data.loader import fetch_ohlcv
from quant_backtester.tickers import TICKERS

START, END = "2018-01-01", "2024-01-01"


def main() -> None:
    for i, (ticker, sector) in enumerate(TICKERS.items(), start=1):
        print(f"[{i}/{len(TICKERS)}] {ticker} ({sector})...", end=" ")
        try:
            df = fetch_ohlcv(ticker, START, END)
            print(f"{len(df)} bars")
        except Exception as exc:
            print(f"FAILED: {exc}")


if __name__ == "__main__":
    main()
