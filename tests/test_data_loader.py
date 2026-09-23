"""Integration tests against a real Postgres instance.

Skipped automatically if DATABASE_URL isn't reachable (e.g. `docker compose
up -d postgres` hasn't been run) -- these are the only tests in the suite
that require a live service, everything else runs against synthetic data.
"""

from __future__ import annotations

import pandas as pd
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from quant_backtester.data.loader import _read_cached, _write_cache, get_database_url


def _make_engine():
    engine = create_engine(get_database_url())
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError:
        pytest.skip("Postgres not reachable -- run `docker compose up -d postgres` and `python scripts/migrate.py`")
    return engine


@pytest.fixture
def engine():
    eng = _make_engine()
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM ohlcv WHERE ticker = '__TEST__'"))
    yield eng
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM ohlcv WHERE ticker = '__TEST__'"))


def test_write_then_read_round_trips(engine):
    dates = pd.bdate_range("2023-01-02", periods=5)
    df = pd.DataFrame(
        {"open": [1.0] * 5, "high": [1.5] * 5, "low": [0.5] * 5, "close": [1.2] * 5, "volume": [100] * 5},
        index=dates,
    )

    _write_cache(engine, "__TEST__", df)
    result = _read_cached(engine, "__TEST__", "2023-01-01", "2023-01-10")

    assert len(result) == 5
    assert list(result["close"]) == [1.2] * 5


def test_upsert_overwrites_existing_row(engine):
    dates = pd.bdate_range("2023-01-02", periods=1)
    df_v1 = pd.DataFrame({"open": [1.0], "high": [1.5], "low": [0.5], "close": [1.2], "volume": [100]}, index=dates)
    df_v2 = pd.DataFrame({"open": [9.0], "high": [9.5], "low": [8.5], "close": [9.2], "volume": [999]}, index=dates)

    _write_cache(engine, "__TEST__", df_v1)
    _write_cache(engine, "__TEST__", df_v2)
    result = _read_cached(engine, "__TEST__", "2023-01-01", "2023-01-10")

    assert len(result) == 1
    assert result["close"].iloc[0] == 9.2


def test_read_cached_empty_range_returns_empty_frame(engine):
    result = _read_cached(engine, "__TEST__", "2023-01-01", "2023-01-10")
    assert result.empty
