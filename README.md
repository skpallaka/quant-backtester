# quant-backtester

A small, from-scratch backtesting engine: data layer, a pluggable strategy
interface, statistically-honest performance metrics, and five strategies
(moving average crossover, RSI, momentum, mean reversion, logistic
regression baseline).

## Layout

```
src/quant_backtester/
  data/loader.py        # yfinance fetch + SQLite cache (cache-first, upserts missing dates)
  engine/strategy.py     # Strategy ABC -- engine knows nothing about strategy internals
  engine/backtest.py      # core day-by-day loop, transaction costs, no-lookahead execution
  engine/validation.py    # time-based (non-shuffled) train/test split
  metrics/metrics.py       # Sharpe ratio, max drawdown, bootstrap confidence intervals
  strategies/               # moving_average, rsi, momentum, mean_reversion, logistic
tests/                       # pytest suite (37 tests) covering all of the above
scripts/run_backtest.py       # end-to-end example: fetch -> split -> backtest -> report
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run the example

```bash
python scripts/run_backtest.py SPY
```

## Run tests

```bash
pytest tests/ -v
```

## Design notes

**Engine/strategy separation.** `BacktestEngine` only ever calls
`strategy.generate_signal(history)`; it has no knowledge of moving
averages, RSI, or anything else strategy-specific. Any new strategy is a
drop-in as long as it implements the `Strategy` ABC.

**Lookahead-bias prevention.** On bar `t`, a strategy sees
`data.iloc[:t+1]` -- everything up to and including bar `t`'s close, never
more. Its signal is filled at bar `t+1`'s *open*, one step after the
strategy could have seen it. There is no code path for a strategy to
trade on a price before that price existed.

**Time-based splits.** `validation.time_based_split` cuts by position, not
shuffled -- train is always chronologically before test. A model (e.g. the
logistic regression baseline) is fit once on train and then walked forward
on test via `generate_signal`, never re-fit on data it's being evaluated
against.

**Transaction costs.** Every rebalance pays `cost_bps` on the traded
notional, deducted from cash at fill time -- so strategies that flip
position constantly get penalized realistically instead of trading for
free.

**Bootstrap confidence intervals.** `metrics.bootstrap_confidence_interval`
resamples the observed return series with replacement (default 1,000
times) and reports the percentile interval of a metric across resamples.
It answers "how much would this point estimate vary by chance alone,"
which is a different (narrower) claim than "will this work
out-of-sample" -- useful for telling a real edge from noise.
