"""Integration tests for the Flask API. Like test_data_loader.py, these need
a live Postgres and are skipped automatically if it's not reachable.

Celery is put in "eager" mode for these tests: `.delay()` runs the task
inline instead of publishing to Redis, so no worker process needs to be
running for the test suite to exercise the full create -> execute -> read
path. It's the standard way to test Celery wiring without a live broker;
the real async behavior (worker picks the job off Redis) is what was
verified manually with `docker compose up -d redis` + a running worker.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from quant_backtester.api.app import create_app
from quant_backtester.api.tasks import celery_app
from quant_backtester.data.loader import get_engine
from tests.test_data_loader import _make_engine


@pytest.fixture
def client():
    _make_engine()  # skips the test if Postgres isn't reachable
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM backtest_runs WHERE ticker IN ('__TEST__', 'AAPL')"))


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_list_strategies(client):
    resp = client.get("/strategies")
    assert resp.status_code == 200
    assert "moving_average_crossover" in resp.get_json()["strategies"]


def test_create_backtest_missing_fields(client):
    resp = client.post("/backtests", json={"ticker": "__TEST__"})
    assert resp.status_code == 400
    assert "missing required fields" in resp.get_json()["error"]


def test_create_backtest_unknown_strategy(client):
    """Strategy name is validated before enqueueing, so this is a synchronous
    400 -- no job is ever created, unlike a failure discovered mid-run."""
    resp = client.post("/backtests", json={
        "ticker": "AAPL", "start": "2023-01-01", "end": "2023-02-01", "strategy": "not_a_real_strategy",
    })
    assert resp.status_code == 400
    assert "Unknown strategy" in resp.get_json()["error"]


def test_create_backtest_returns_pending_immediately(client):
    create_resp = client.post("/backtests", json={
        "ticker": "AAPL", "start": "2023-01-01", "end": "2023-03-01",
        "strategy": "momentum", "strategy_params": {"lookback": 10},
    })
    assert create_resp.status_code == 202
    body = create_resp.get_json()
    assert body["status"] == "pending"
    assert "id" in body


def test_job_completes_and_is_readable_after_enqueue(client):
    """With Celery in eager mode, `.delay()` inside the route already ran the
    task synchronously by the time POST returns -- so GET right after should
    see the completed result, proving create -> task -> DB write all wired
    up correctly."""
    create_resp = client.post("/backtests", json={
        "ticker": "AAPL", "start": "2023-01-01", "end": "2023-03-01",
        "strategy": "momentum", "strategy_params": {"lookback": 10},
    })
    run_id = create_resp.get_json()["id"]

    get_resp = client.get(f"/backtests/{run_id}")
    assert get_resp.status_code == 200
    fetched = get_resp.get_json()
    assert fetched["status"] == "completed"
    assert "sharpe_ratio" in fetched["result"]["metrics"]
    assert "equity_curve" in fetched["result"]


def test_job_failure_mid_run_sets_failed_status(client):
    """Invalid strategy_params (caught at construction, not at the earlier
    strategy-name check) should surface as a failed job, not a 500 -- proof
    the task's except-and-record-error path works, not just the happy path."""
    create_resp = client.post("/backtests", json={
        "ticker": "AAPL", "start": "2023-01-01", "end": "2023-03-01",
        "strategy": "moving_average_crossover", "strategy_params": {"short_window": 50, "long_window": 20},
    })
    run_id = create_resp.get_json()["id"]

    fetched = client.get(f"/backtests/{run_id}").get_json()
    assert fetched["status"] == "failed"
    assert fetched["error"]


def test_get_nonexistent_backtest_returns_404(client):
    resp = client.get("/backtests/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


def test_list_backtests_after_creation(client):
    client.post("/backtests", json={
        "ticker": "AAPL", "start": "2023-01-01", "end": "2023-02-01", "strategy": "rsi",
    })
    resp = client.get("/backtests")
    assert resp.status_code == 200
    runs = resp.get_json()
    assert isinstance(runs, list)
    assert len(runs) >= 1
