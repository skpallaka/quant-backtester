"""Time-based train/test splitting.

A random split leaks the future into the past: if day 500 lands in train
and day 300 lands in test, a model fit on train has effectively seen
information from after the test period (autocorrelated features, a
regime shift, anything correlated with time). Financial time series data
must be split at a cutoff DATE, never shuffled, so training data is always
strictly earlier than everything it will be evaluated against.
"""

from __future__ import annotations

import pandas as pd


def time_based_split(data: pd.DataFrame, test_size: float = 0.2) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split `data` (sorted ascending by date) into (train, test) by position.

    The last `test_size` fraction of rows becomes the test set; everything
    before it is train. No shuffling -- train is always chronologically
    earlier than test.
    """
    if not data.index.is_monotonic_increasing:
        raise ValueError("data must be sorted ascending by date before splitting")
    if not 0.0 < test_size < 1.0:
        raise ValueError("test_size must be in (0, 1)")

    split_idx = int(len(data) * (1 - test_size))
    train = data.iloc[:split_idx]
    test = data.iloc[split_idx:]
    return train, test
