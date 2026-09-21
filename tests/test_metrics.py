import numpy as np
import pytest

from quant_backtester.metrics.metrics import bootstrap_confidence_interval, max_drawdown, sharpe_ratio


def test_sharpe_ratio_zero_volatility_returns_zero():
    returns = np.full(50, 0.001)
    assert sharpe_ratio(returns) == 0.0


def test_sharpe_ratio_positive_for_consistently_positive_excess_returns():
    rng = np.random.default_rng(0)
    returns = rng.normal(loc=0.001, scale=0.005, size=500)
    assert sharpe_ratio(returns) > 0


def test_sharpe_ratio_empty_series():
    assert sharpe_ratio(np.array([])) == 0.0


def test_sharpe_ratio_known_value():
    # Constant excess return with known std -> Sharpe should match closed form.
    returns = np.array([0.01, -0.01, 0.02, -0.02, 0.01, -0.01, 0.02, -0.02])
    expected = np.sqrt(252) * returns.mean() / returns.std(ddof=1)
    assert sharpe_ratio(returns, periods_per_year=252) == pytest.approx(expected)


def test_max_drawdown_known_sequence():
    equity = np.array([100, 110, 90, 120, 60, 130])
    # peak 110 -> trough 90: -18.18%; peak 120 -> trough 60: -50%. Worst is -50%.
    assert max_drawdown(equity) == pytest.approx(-0.5)


def test_max_drawdown_monotonic_increase_is_zero():
    equity = np.array([100, 101, 102, 103, 104])
    assert max_drawdown(equity) == pytest.approx(0.0)


def test_max_drawdown_empty_series():
    assert max_drawdown(np.array([])) == 0.0


def test_bootstrap_ci_contains_point_estimate():
    rng = np.random.default_rng(1)
    returns = rng.normal(loc=0.001, scale=0.01, size=300)
    result = bootstrap_confidence_interval(returns, n_resamples=500, random_state=1)
    assert result["lower"] <= result["point_estimate"] <= result["upper"]
    assert len(result["resamples"]) == 500


def test_bootstrap_ci_narrows_with_lower_variance_data():
    rng = np.random.default_rng(2)
    low_var = rng.normal(loc=0.001, scale=0.001, size=300)
    high_var = rng.normal(loc=0.001, scale=0.05, size=300)

    low_result = bootstrap_confidence_interval(low_var, n_resamples=500, random_state=2)
    high_result = bootstrap_confidence_interval(high_var, n_resamples=500, random_state=2)

    low_width = low_result["upper"] - low_result["lower"]
    high_width = high_result["upper"] - high_result["lower"]
    assert low_width < high_width


def test_bootstrap_ci_empty_series():
    result = bootstrap_confidence_interval(np.array([]))
    assert result["point_estimate"] == 0.0
    assert result["lower"] == 0.0
    assert result["upper"] == 0.0
