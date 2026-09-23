"""Celery app + the async backtest task.

Same logic Day 10's Flask route ran inline (call run_backtest, write the
result to backtest_runs), just moved off the request thread. Redis is both
the broker (queues the job) and the result backend (though we don't use
Celery's result backend for reads -- the API reads status/result straight
from Postgres so `GET /backtests/:id` doesn't need to know anything about
Celery).
"""

from __future__ import annotations

import json
import os

from celery import Celery
from sqlalchemy import text

from quant_backtester.api.runner import run_backtest
from quant_backtester.data.loader import get_engine

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery("quant_backtester", broker=REDIS_URL, backend=REDIS_URL)


@celery_app.task(name="run_backtest_task")
def run_backtest_task(run_id: str, params: dict) -> None:
    engine = get_engine()

    with engine.begin() as conn:
        conn.execute(text("UPDATE backtest_runs SET status = 'running' WHERE id = :id"), {"id": run_id})

    try:
        result = run_backtest(params)
    except Exception as exc:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE backtest_runs SET status = 'failed', error = :err, completed_at = now()
                    WHERE id = :id
                """),
                {"err": str(exc), "id": run_id},
            )
        return

    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE backtest_runs SET status = 'completed', result = :result, completed_at = now()
                WHERE id = :id
            """),
            {"result": json.dumps(result), "id": run_id},
        )
