"""Shared ticker universe, grouped by sector.

Used by both scripts/run_backtest_grid.py (pandas-based strategy backtests)
and scripts/spark_analysis.py (PySpark aggregation) so both draw from the
same set instead of maintaining separate lists.
"""

from __future__ import annotations

TICKERS: dict[str, str] = {
    # index / ETF
    "SPY": "index_etf",
    "QQQ": "index_etf",
    "IWM": "index_etf",
    "TLT": "index_etf",
    "DIA": "index_etf",
    "GLD": "index_etf",
    # mega-cap tech
    "AAPL": "mega_cap_tech",
    "MSFT": "mega_cap_tech",
    "NVDA": "mega_cap_tech",
    "GOOGL": "mega_cap_tech",
    "AMZN": "mega_cap_tech",
    "META": "mega_cap_tech",
    "AVGO": "mega_cap_tech",
    # financials
    "JPM": "financials",
    "BAC": "financials",
    "GS": "financials",
    "WFC": "financials",
    # healthcare
    "JNJ": "healthcare",
    "PFE": "healthcare",
    "UNH": "healthcare",
    "MRK": "healthcare",
    # energy
    "XOM": "energy",
    "CVX": "energy",
    # consumer
    "WMT": "consumer",
    "PG": "consumer",
    "KO": "consumer",
    "MCD": "consumer",
    # industrials
    "BA": "industrials",
    "CAT": "industrials",
    "GE": "industrials",
    # communication / media
    "DIS": "communication",
    "NFLX": "communication",
    "VZ": "communication",
    # auto / EV
    "TSLA": "auto",
}
