"""OHLCV data access: fetch from Yahoo Finance, cache to SQLite.

The cache is keyed on (ticker, date). Repeated calls for a range that's
already cached hit SQLite only; anything missing is pulled from yfinance
and upserted before returning.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

DEFAULT_DB_PATH = Path(__file__).resolve().parents[3] / "data_cache" / "market_data.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ohlcv (
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume INTEGER NOT NULL,
    PRIMARY KEY (ticker, date)
);
"""


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(_SCHEMA)
    return conn


def _read_cached(conn: sqlite3.Connection, ticker: str, start: str, end: str) -> pd.DataFrame:
    query = """
        SELECT date, open, high, low, close, volume
        FROM ohlcv
        WHERE ticker = ? AND date >= ? AND date < ?
        ORDER BY date ASC
    """
    df = pd.read_sql_query(query, conn, params=(ticker, start, end), parse_dates=["date"])
    return df.set_index("date")


def _write_cache(conn: sqlite3.Connection, ticker: str, df: pd.DataFrame) -> None:
    if df.empty:
        return
    rows = [
        (ticker, idx.strftime("%Y-%m-%d"), float(row["open"]), float(row["high"]), float(row["low"]),
         float(row["close"]), int(row["volume"]))
        for idx, row in df.iterrows()
    ]
    conn.executemany(
        """
        INSERT INTO ohlcv (ticker, date, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker, date) DO UPDATE SET
            open=excluded.open, high=excluded.high, low=excluded.low,
            close=excluded.close, volume=excluded.volume
        """,
        rows,
    )
    conn.commit()


def _fetch_from_yfinance(ticker: str, start: str, end: str) -> pd.DataFrame:
    import yfinance as yf

    raw = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
    if raw.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    raw = raw.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
    raw.index.name = "date"
    return raw


def fetch_ohlcv(ticker: str, start: str, end: str, db_path: Path = DEFAULT_DB_PATH) -> pd.DataFrame:
    """Return daily OHLCV for `ticker` in [start, end), cache-first.

    Dates missing from the local SQLite cache are pulled from Yahoo Finance
    and persisted before the combined frame is returned.
    """
    conn = _connect(db_path)
    try:
        cached = _read_cached(conn, ticker, start, end)
        expected_days = pd.bdate_range(start, end, inclusive="left")
        missing = expected_days.difference(cached.index)

        if len(missing) > 0:
            fresh = _fetch_from_yfinance(ticker, start, end)
            _write_cache(conn, ticker, fresh)
            cached = _read_cached(conn, ticker, start, end)

        return cached
    finally:
        conn.close()
