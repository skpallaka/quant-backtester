import pandas as pd
import pytest

from quant_backtester.engine.backtest import BacktestEngine
from quant_backtester.engine.strategy import BuyAndHoldStrategy, Strategy
from quant_backtester.metrics.metrics import max_drawdown, sharpe_ratio
from quant_backtester.strategies.moving_average import MovingAverageCrossover


def test_engine_rejects_missing_columns():
    bad_data = pd.DataFrame({"close": [1, 2, 3]}, index=pd.bdate_range("2023-01-01", periods=3))
    with pytest.raises(ValueError):
        BacktestEngine(bad_data, BuyAndHoldStrategy())


def test_engine_rejects_unsorted_data(synthetic_ohlcv):
    reversed_data = synthetic_ohlcv.iloc[::-1]
    with pytest.raises(ValueError):
        BacktestEngine(reversed_data, BuyAndHoldStrategy())


def test_buy_and_hold_equity_curve_length_matches_data(synthetic_ohlcv):
    result = BacktestEngine(synthetic_ohlcv, BuyAndHoldStrategy()).run()
    assert len(result.equity_curve) == len(synthetic_ohlcv)
    assert result.equity_curve.index.equals(synthetic_ohlcv.index)


def test_buy_and_hold_tracks_underlying_after_initial_trade(synthetic_ohlcv):
    result = BacktestEngine(synthetic_ohlcv, BuyAndHoldStrategy(), cost_bps=0.0).run()
    underlying_return = synthetic_ohlcv["close"].iloc[-1] / synthetic_ohlcv["close"].iloc[1] - 1
    strategy_return = result.equity_curve.iloc[-1] / result.equity_curve.iloc[1] - 1
    assert strategy_return == pytest.approx(underlying_return, abs=0.01)


def test_transaction_costs_reduce_equity_vs_zero_cost(synthetic_ohlcv):
    strategy_factory = lambda: MovingAverageCrossover(short_window=5, long_window=20)
    no_cost = BacktestEngine(synthetic_ohlcv, strategy_factory(), cost_bps=0.0).run()
    with_cost = BacktestEngine(synthetic_ohlcv, strategy_factory(), cost_bps=50.0).run()
    assert with_cost.equity_curve.iloc[-1] <= no_cost.equity_curve.iloc[-1]


def test_flat_strategy_never_trades(synthetic_ohlcv):
    class AlwaysFlat(Strategy):
        warmup_period = 0

        def generate_signal(self, history):
            return 0.0

    result = BacktestEngine(synthetic_ohlcv, AlwaysFlat()).run()
    assert len(result.trades) == 0
    assert (result.equity_curve == result.equity_curve.iloc[0]).all()


def test_signal_never_receives_future_rows(synthetic_ohlcv):
    """Instrument the strategy to record the last visible date on each call and
    assert it's never later than the bar the engine is currently on."""
    seen_max_dates = []

    class RecordingStrategy(Strategy):
        warmup_period = 5

        def generate_signal(self, history):
            seen_max_dates.append(history.index[-1])
            return 1.0

    BacktestEngine(synthetic_ohlcv, RecordingStrategy()).run()

    for call_index, seen_date in enumerate(seen_max_dates):
        bar_index = call_index + 5
        assert seen_date == synthetic_ohlcv.index[bar_index]
        assert seen_date <= synthetic_ohlcv.index[bar_index]


def test_full_backtest_end_to_end_with_metrics(synthetic_ohlcv):
    result = BacktestEngine(synthetic_ohlcv, MovingAverageCrossover(short_window=10, long_window=30)).run()

    sharpe = sharpe_ratio(result.returns)
    mdd = max_drawdown(result.equity_curve)

    assert isinstance(sharpe, float)
    assert mdd <= 0.0
    assert result.equity_curve.iloc[-1] > 0
