"""Logistic regression baseline strategy.

Predicts the sign of next-bar return from a handful of engineered features
(recent returns, a short/long MA ratio, realized volatility, RSI), fit once
on a training slice via `fit()`. The backtest only ever calls
`generate_signal(history)` on the test slice, and features there are built
purely from `history` (rows up to and including the current bar) -- the
model was never shown test-period data during fitting, and never sees a
future row during prediction. This is what "time-based train/test split"
in validation.py exists to enforce: fit on data.loc[:split_date] only.
"""

from __future__ import annotations

import pandas as pd
from sklearn.linear_model import LogisticRegression

from quant_backtester.engine.strategy import Strategy

_FEATURE_WARMUP = 20


def _build_features(data: pd.DataFrame) -> pd.DataFrame:
    close = data["close"]
    feats = pd.DataFrame(index=data.index)
    feats["ret_1"] = close.pct_change(1)
    feats["ret_5"] = close.pct_change(5)
    feats["ma_ratio"] = close.rolling(5).mean() / close.rolling(_FEATURE_WARMUP).mean() - 1.0
    feats["volatility"] = close.pct_change().rolling(10).std()

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0.0, float("nan"))
    feats["rsi"] = (100.0 - 100.0 / (1.0 + rs)).fillna(50.0)

    return feats


class LogisticRegressionStrategy(Strategy):
    """Long if P(next bar up) > threshold, else flat/short. Must call `fit()` before use."""

    warmup_period = _FEATURE_WARMUP + 1

    def __init__(self, threshold: float = 0.5, allow_short: bool = False, **lr_kwargs):
        self.threshold = threshold
        self.allow_short = allow_short
        self.model = LogisticRegression(max_iter=1000, **lr_kwargs)
        self._fitted = False

    def fit(self, train_data: pd.DataFrame) -> "LogisticRegressionStrategy":
        """Fit on `train_data` only. Labels use next-bar direction (fine for
        training targets -- we know the training set's own future), but
        `train_data` itself must be strictly earlier than anything the
        engine will later show `generate_signal` at test time.
        """
        feats = _build_features(train_data)
        label = (train_data["close"].shift(-1) > train_data["close"]).astype(int)

        frame = feats.copy()
        frame["label"] = label
        frame = frame.dropna()

        self.model.fit(frame[feats.columns], frame["label"])
        self._fitted = True
        return self

    def generate_signal(self, history: pd.DataFrame) -> float:
        if not self._fitted:
            raise RuntimeError("LogisticRegressionStrategy.fit(train_data) must be called before backtesting")

        feats = _build_features(history)
        latest = feats.iloc[[-1]]
        if latest.isna().any(axis=None):
            return 0.0

        proba_up = self.model.predict_proba(latest)[0, 1]
        if proba_up > self.threshold:
            return 1.0
        return -1.0 if self.allow_short else 0.0
