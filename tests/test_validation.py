import pytest

from quant_backtester.engine.validation import time_based_split


def test_split_is_chronological_not_shuffled(synthetic_ohlcv):
    train, test = time_based_split(synthetic_ohlcv, test_size=0.2)
    assert train.index.max() < test.index.min()


def test_split_sizes_roughly_match_requested_fraction(synthetic_ohlcv):
    train, test = time_based_split(synthetic_ohlcv, test_size=0.2)
    assert len(train) + len(test) == len(synthetic_ohlcv)
    assert len(test) / len(synthetic_ohlcv) == pytest.approx(0.2, abs=0.01)


def test_split_rejects_unsorted_data(synthetic_ohlcv):
    with pytest.raises(ValueError):
        time_based_split(synthetic_ohlcv.iloc[::-1], test_size=0.2)


def test_split_rejects_invalid_test_size(synthetic_ohlcv):
    with pytest.raises(ValueError):
        time_based_split(synthetic_ohlcv, test_size=1.5)
