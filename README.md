# quant-backtester

A small, from-scratch backtesting engine: data layer, a pluggable strategy
interface, statistically-honest performance metrics, and five strategies
(moving average crossover, RSI, momentum, mean reversion, logistic
regression baseline) -- backed by a Postgres-backed Flask API with async
backtest execution via Celery/Redis.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for a diagram of the full
system (what's built vs. what's still planned on AWS) and the reasoning
behind each major decision.

## Layout

```
src/quant_backtester/
  data/loader.py        # yfinance fetch + Postgres cache (cache-first, upserts missing dates)
  engine/strategy.py     # Strategy ABC -- engine knows nothing about strategy internals
  engine/backtest.py      # core day-by-day loop, transaction costs, no-lookahead execution
  engine/validation.py    # time-based (non-shuffled) train/test split
  metrics/metrics.py       # Sharpe ratio, max drawdown, bootstrap confidence intervals
  strategies/               # moving_average, rsi, momentum, mean_reversion, logistic
  api/app.py                # Flask REST API: enqueue backtests, read back results
  api/tasks.py                # Celery app + the async backtest task (runs on a worker, not the request thread)
  api/runner.py                 # pure fetch -> backtest -> metrics function, shared by API and worker
  api/registry.py                 # strategy name -> class, for the API's strategy_params contract
  logging_config.py                 # JSON log formatter -- same stdout output CloudWatch will later ingest
migrations/                        # versioned SQL schema, applied by scripts/migrate.py
tests/                               # pytest suite (49 tests) covering all of the above
scripts/run_backtest.py               # end-to-end example: fetch -> split -> backtest -> report
scripts/migrate.py                     # idempotent schema migration runner (local Postgres or RDS)
docker-compose.yml                      # local Postgres + Redis for development
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# start Postgres + Redis and apply the schema
docker compose up -d
cp .env.example .env   # edit DATABASE_URL / REDIS_URL if not using the defaults above
python scripts/migrate.py
```

`DATABASE_URL` defaults to `postgresql+psycopg://quant:quant@localhost:5432/quant_backtester`
and `REDIS_URL` to `redis://localhost:6379/0` (matching docker-compose.yml)
if unset -- override `DATABASE_URL` to point at RDS once that exists.

## Run the example

```bash
python scripts/run_backtest.py SPY
```

## Run the API

Three processes: Postgres/Redis (already up via docker compose), the
Celery worker, and Flask -- in separate terminals:

```bash
# terminal 1: worker
celery -A quant_backtester.api.tasks:celery_app worker --loglevel=info --pool=solo

# terminal 2: API
export FLASK_APP=quant_backtester.api.app:app
flask run --port 5050
```

`--pool=solo` is a macOS/Python 3.13 workaround -- Celery's default
prefork pool crashes on `billiard` fork setup on this combination. Drop
the flag on Linux (e.g. inside the eventual ECS task).

```bash
curl -X POST localhost:5050/backtests -H "Content-Type: application/json" -d '{
  "ticker": "SPY", "start": "2023-01-01", "end": "2023-06-01",
  "strategy": "moving_average_crossover", "strategy_params": {"short_window": 10, "long_window": 30}
}'
# -> {"id": "...", "status": "pending"}   (returns immediately; worker runs the backtest)

curl localhost:5050/backtests/<id>     # poll: pending -> running -> completed/failed
curl localhost:5050/backtests          # list recent runs
curl localhost:5050/strategies         # what strategy names are valid
```

## Run tests

```bash
pytest tests/ -v
```

Most tests run against synthetic data and need nothing running. Tests in
`test_data_loader.py` and `test_api.py` need Postgres and are skipped
automatically if `docker compose up -d postgres` hasn't been run.
`test_api.py` runs Celery in "eager" mode (`.delay()` executes inline) so
it doesn't need a live worker or Redis to verify the create -> execute ->
read wiring -- the real async path was verified manually against a running
worker + Redis.

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

**Async jobs over blocking requests.** `POST /backtests` used to run the
backtest inline and return the full result. Once a backtest covers years
of data and a 1,000-resample bootstrap, that can take minutes -- far past
any reasonable HTTP timeout. Now the route does three cheap things
(validate, insert a `pending` row, enqueue) and returns in milliseconds;
`api/tasks.py`'s Celery task does the actual work on a separate worker
process and writes the result back to the same `backtest_runs` row a
client is already polling via `GET /backtests/:id`. `api/runner.py` is the
same pure function either way -- the only thing that changed between Day
10 and Day 11 is who calls it and when.

**Structured logging.** `logging_config.py` formats every log line as JSON
and both `api/app.py` (HTTP requests) and `api/tasks.py` (job lifecycle:
`backtest_started`/`backtest_completed`/`backtest_failed`, each with
`run_id`, timing, and outcome) log through it. Locally that's just
readable JSON on stdout. Once this runs on ECS, the same stdout gets
shipped to CloudWatch Logs by the awslogs driver with zero code changes --
"how would you know if this broke at 3am" becomes: a CloudWatch alarm on
the rate of `backtest_failed` events (or on `http_request` entries with
`status >= 500`) pages on-call, and Logs Insights can filter straight to
`{ $.run_id = "..." }` to pull the exact failure instead of grepping raw
text. That alarm wiring is Day 14/AWS work not yet done -- what exists
today is the structured logs it would consume.

One gotcha worth knowing: Celery's worker replaces the root logger's
handlers on startup (`worker_hijack_root_logger`), so calling
`configure_logging()` at import time in `tasks.py` gets silently
discarded the moment the worker boots. The fix is connecting to Celery's
`setup_logging` signal instead, which runs after Celery's own logging
setup and opts out of it -- see the `_configure_worker_logging` receiver
in `api/tasks.py`.

**Bootstrap confidence intervals.** `metrics.bootstrap_confidence_interval`
resamples the observed return series with replacement (default 1,000
times) and reports the percentile interval of a metric across resamples.
It answers "how much would this point estimate vary by chance alone,"
which is a different (narrower) claim than "will this work
out-of-sample" -- useful for telling a real edge from noise.
