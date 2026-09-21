import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def synthetic_ohlcv():
    """Deterministic synthetic OHLCV data -- no network dependency for tests."""
    rng = np.random.default_rng(42)
    n = 250
    dates = pd.bdate_range("2022-01-03", periods=n)
    log_returns = rng.normal(loc=0.0003, scale=0.012, size=n)
    close = 100.0 * np.exp(np.cumsum(log_returns))
    open_ = close * (1 + rng.normal(0, 0.001, size=n))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.002, size=n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.002, size=n)))
    volume = rng.integers(1_000_000, 5_000_000, size=n)

    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )
