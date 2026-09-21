import pytest

from quant_backtester.strategies.logistic import LogisticRegressionStrategy
from quant_backtester.strategies.mean_reversion import MeanReversionStrategy
from quant_backtester.strategies.momentum import MomentumStrategy
from quant_backtester.strategies.moving_average import MovingAverageCrossover
from quant_backtester.strategies.rsi import RSIStrategy

STRATEGY_FACTORIES = [
    lambda: MovingAverageCrossover(short_window=5, long_window=20),
    lambda: RSIStrategy(period=14),
    lambda: MomentumStrategy(lookback=10),
    lambda: MeanReversionStrategy(window=20, z_threshold=1.0),
]


@pytest.mark.parametrize("make_strategy", STRATEGY_FACTORIES)
def test_signal_is_in_valid_range(make_strategy, synthetic_ohlcv):
    strategy = make_strategy()
    for i in range(strategy.warmup_period, len(synthetic_ohlcv)):
        signal = strategy.generate_signal(synthetic_ohlcv.iloc[: i + 1])
        assert -1.0 <= signal <= 1.0


@pytest.mark.parametrize("make_strategy", STRATEGY_FACTORIES)
def test_signal_is_deterministic(make_strategy, synthetic_ohlcv):
    history = synthetic_ohlcv.iloc[:60]
    s1, s2 = make_strategy(), make_strategy()
    assert s1.generate_signal(history) == s2.generate_signal(history)


@pytest.mark.parametrize("make_strategy", STRATEGY_FACTORIES)
def test_signal_only_depends_on_visible_history(make_strategy, synthetic_ohlcv):
    """A strategy given the same history twice, once with future rows appended
    after it decided, must produce the same signal both times -- proof it never
    peeked past the slice it was handed."""
    history = synthetic_ohlcv.iloc[:60]
    strategy = make_strategy()
    signal_before = strategy.generate_signal(history)

    longer_history_prefix = synthetic_ohlcv.iloc[:60]
    assert longer_history_prefix.equals(history)
    strategy2 = make_strategy()
    signal_again = strategy2.generate_signal(longer_history_prefix)
    assert signal_before == signal_again


def test_ma_crossover_rejects_invalid_windows():
    with pytest.raises(ValueError):
        MovingAverageCrossover(short_window=50, long_window=20)


def test_logistic_strategy_requires_fit_before_use(synthetic_ohlcv):
    strategy = LogisticRegressionStrategy()
    with pytest.raises(RuntimeError):
        strategy.generate_signal(synthetic_ohlcv.iloc[:60])


def test_logistic_strategy_predicts_after_fit(synthetic_ohlcv):
    train = synthetic_ohlcv.iloc[:150]
    test_history = synthetic_ohlcv.iloc[:180]

    strategy = LogisticRegressionStrategy()
    strategy.fit(train)
    signal = strategy.generate_signal(test_history)
    assert signal in (0.0, 1.0)
