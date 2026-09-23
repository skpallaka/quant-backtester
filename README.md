# quant-backtester

A small, from-scratch backtesting engine: data layer, a pluggable strategy
interface, statistically-honest performance metrics, and five strategies
(moving average crossover, RSI, momentum, mean reversion, logistic
regression baseline).

## Layout

```
src/quant_backtester/
  data/loader.py        # yfinance fetch + Postgres cache (cache-first, upserts missing dates)
  engine/strategy.py     # Strategy ABC -- engine knows nothing about strategy internals
  engine/backtest.py      # core day-by-day loop, transaction costs, no-lookahead execution
  engine/validation.py    # time-based (non-shuffled) train/test split
  metrics/metrics.py       # Sharpe ratio, max drawdown, bootstrap confidence intervals
  strategies/               # moving_average, rsi, momentum, mean_reversion, logistic
  api/app.py                # Flask REST API: run backtests, read back results
  api/runner.py               # pure fetch -> backtest -> metrics function, shared by API and (later) workers
  api/registry.py               # strategy name -> class, for the API's strategy_params contract
migrations/                      # versioned SQL schema, applied by scripts/migrate.py
tests/                             # pytest suite (47 tests) covering all of the above
scripts/run_backtest.py             # end-to-end example: fetch -> split -> backtest -> report
scripts/migrate.py                   # idempotent schema migration runner (local Postgres or RDS)
docker-compose.yml                    # local Postgres for development
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# start Postgres and apply the schema
docker compose up -d postgres
cp .env.example .env   # edit DATABASE_URL if not using the default local Postgres
python scripts/migrate.py
```

`DATABASE_URL` defaults to `postgresql+psycopg://quant:quant@localhost:5432/quant_backtester`
(matching docker-compose.yml) if unset -- override it to point at RDS or
anything else Postgres-compatible.

## Run the example

```bash
python scripts/run_backtest.py SPY
```

## Run the API

```bash
export FLASK_APP=quant_backtester.api.app:app
flask run --port 5050
```

```bash
curl -X POST localhost:5050/backtests -H "Content-Type: application/json" -d '{
  "ticker": "SPY", "start": "2023-01-01", "end": "2023-06-01",
  "strategy": "moving_average_crossover", "strategy_params": {"short_window": 10, "long_window": 30}
}'
# -> {"id": "...", "status": "completed", "metrics": {...}, "equity_curve": [...]}

curl localhost:5050/backtests/<id>     # fetch a stored run
curl localhost:5050/backtests          # list recent runs
curl localhost:5050/strategies         # what strategy names are valid
```

Requests block until the backtest finishes -- fine for the date ranges
above, not fine once a request means years of data and thousands of
bootstrap resamples. That's what Day 11 (Redis + Celery) exists to fix.

## Run tests

```bash
pytest tests/ -v
```

Most tests run against synthetic data and need nothing running. A handful
in `test_data_loader.py` exercise the real Postgres cache and are skipped
automatically if `docker compose up -d postgres` hasn't been run.

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

**Postgres over SQLite.** The cache started on SQLite because it needed
zero setup for a single-machine, single-process prototype. Postgres is the
swap once the plan includes a server process handling concurrent requests
(Day 10) and background workers writing results (Day 11) -- SQLite's
single-writer model doesn't hold up once more than one process touches the
database at a time. Schema changes go through `migrations/*.sql` +
`scripts/migrate.py` rather than ad hoc `CREATE TABLE IF NOT EXISTS` calls,
so the same migration path works against local Docker Postgres and RDS.

**Bootstrap confidence intervals.** `metrics.bootstrap_confidence_interval`
resamples the observed return series with replacement (default 1,000
times) and reports the percentile interval of a metric across resamples.
It answers "how much would this point estimate vary by chance alone,"
which is a different (narrower) claim than "will this work
out-of-sample" -- useful for telling a real edge from noise.
