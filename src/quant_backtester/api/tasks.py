"""Celery app + the async backtest task.

Same logic the original synchronous Flask route ran inline (call run_backtest, write the
result to backtest_runs), just moved off the request thread. Redis is both
the broker (queues the job) and the result backend (though we don't use
Celery's result backend for reads -- the API reads status/result straight
from Postgres so `GET /backtests/:id` doesn't need to know anything about
Celery).
"""

from __future__ import annotations

import json
import logging
import os
import time

from celery import Celery
from celery.signals import setup_logging
from sqlalchemy import text

from quant_backtester.api.runner import run_backtest
from quant_backtester.data.loader import get_engine
from quant_backtester.logging_config import configure_logging, log_event

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery("quant_backtester", broker=REDIS_URL, backend=REDIS_URL)

logger = logging.getLogger("quant_backtester.worker")


@setup_logging.connect
def _configure_worker_logging(**kwargs):
    """Celery's worker replaces the root logger's handlers on startup
    (`worker_hijack_root_logger`) -- connecting to this signal is the
    documented way to opt out and install our own JSON handler instead of
    losing it to Celery's default config.
    """
    configure_logging()


@celery_app.task(name="run_backtest_task")
def run_backtest_task(run_id: str, params: dict) -> None:
    engine = get_engine()
    started = time.monotonic()

    log_event(
        logger, logging.INFO, "backtest_started",
        run_id=run_id, ticker=params.get("ticker"), strategy=params.get("strategy"),
    )

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
        log_event(
            logger, logging.ERROR, "backtest_failed",
            run_id=run_id, error=str(exc), duration_ms=round((time.monotonic() - started) * 1000, 2),
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

    log_event(
        logger, logging.INFO, "backtest_completed",
        run_id=run_id, duration_ms=round((time.monotonic() - started) * 1000, 2),
        sharpe_ratio=result["metrics"]["sharpe_ratio"], num_trades=result["metrics"]["num_trades"],
    )
