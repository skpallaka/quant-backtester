"""Integration tests for the Flask API. Like test_data_loader.py, these need
a live Postgres and are skipped automatically if it's not reachable.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from quant_backtester.api.app import create_app
from quant_backtester.data.loader import get_engine
from tests.test_data_loader import _make_engine


@pytest.fixture
def client():
    _make_engine()  # skips the test if Postgres isn't reachable
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
    resp = client.post("/backtests", json={
        "ticker": "AAPL", "start": "2023-01-01", "end": "2023-02-01", "strategy": "not_a_real_strategy",
    })
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["status"] == "failed"
    assert "Unknown strategy" in body["error"]


def test_create_and_fetch_backtest(client):
    create_resp = client.post("/backtests", json={
        "ticker": "AAPL", "start": "2023-01-01", "end": "2023-03-01",
        "strategy": "momentum", "strategy_params": {"lookback": 10},
    })
    assert create_resp.status_code == 201
    body = create_resp.get_json()
    assert body["status"] == "completed"
    assert "metrics" in body and "equity_curve" in body
    assert "sharpe_ratio" in body["metrics"]

    run_id = body["id"]
    get_resp = client.get(f"/backtests/{run_id}")
    assert get_resp.status_code == 200
    fetched = get_resp.get_json()
    assert fetched["status"] == "completed"
    assert fetched["result"]["metrics"]["sharpe_ratio"] == body["metrics"]["sharpe_ratio"]


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
