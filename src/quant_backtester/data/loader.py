"""OHLCV data access: fetch from Yahoo Finance, cache to Postgres.

The cache is keyed on (ticker, date). Repeated calls for a range that's
already cached hit Postgres only; anything missing is pulled from yfinance
and upserted before returning. Schema lives in migrations/ and is applied
via scripts/migrate.py -- this module assumes the `ohlcv` table already
exists (same requirement whether pointed at local Docker Postgres or RDS).
"""

from __future__ import annotations

import os

import pandas as pd
from sqlalchemy import Engine, create_engine, text

DEFAULT_DATABASE_URL = "postgresql+psycopg://quant:quant@localhost:5432/quant_backtester"

_engine: Engine | None = None


def get_database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def get_engine() -> Engine:
    """Module-level engine, lazily created and reused across calls."""
    global _engine
    if _engine is None:
        _engine = create_engine(get_database_url())
    return _engine


def _read_cached(engine: Engine, ticker: str, start: str, end: str) -> pd.DataFrame:
    query = text("""
        SELECT date, open, high, low, close, volume
        FROM ohlcv
        WHERE ticker = :ticker AND date >= :start AND date < :end
        ORDER BY date ASC
    """)
    df = pd.read_sql_query(
        query, engine, params={"ticker": ticker, "start": start, "end": end}, parse_dates=["date"]
    )
    return df.set_index("date")


def _write_cache(engine: Engine, ticker: str, df: pd.DataFrame) -> None:
    if df.empty:
        return

    rows = [
        {
            "ticker": ticker,
            "date": idx.strftime("%Y-%m-%d"),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": int(row["volume"]),
        }
        for idx, row in df.iterrows()
    ]

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO ohlcv (ticker, date, open, high, low, close, volume)
                VALUES (:ticker, :date, :open, :high, :low, :close, :volume)
                ON CONFLICT (ticker, date) DO UPDATE SET
                    open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
                    close = EXCLUDED.close, volume = EXCLUDED.volume
            """),
            rows,
        )


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


def fetch_ohlcv(ticker: str, start: str, end: str, engine: Engine | None = None) -> pd.DataFrame:
    """Return daily OHLCV for `ticker` in [start, end), cache-first.

    Dates missing from the Postgres cache are pulled from Yahoo Finance and
    persisted before the combined frame is returned. Pass `engine` to target
    a specific database (tests, RDS); defaults to `get_engine()`, which
    reads DATABASE_URL.
    """
    engine = engine or get_engine()

    cached = _read_cached(engine, ticker, start, end)
    expected_days = pd.bdate_range(start, end, inclusive="left")
    missing = expected_days.difference(cached.index)

    if len(missing) > 0:
        fresh = _fetch_from_yfinance(ticker, start, end)
        _write_cache(engine, ticker, fresh)
        cached = _read_cached(engine, ticker, start, end)

    return cached
