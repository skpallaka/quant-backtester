"""Flask REST API for running backtests and reading back results.

POST /backtests enqueues a Celery task and returns immediately with
status='pending' -- the actual backtest runs on a worker process, not the
request thread. This is the fix for backtests that take minutes: an HTTP
request can't sit open that long, but a queued job can run as long as it
needs to while the client polls GET /backtests/:id for status.
"""

from __future__ import annotations

import json
import logging
import time
import uuid

from flask import Flask, g, jsonify, request
from sqlalchemy import text

from quant_backtester.api.registry import available_strategies
from quant_backtester.api.tasks import run_backtest_task
from quant_backtester.data.loader import get_engine
from quant_backtester.logging_config import configure_logging, log_event

REQUIRED_FIELDS = {"ticker", "start", "end", "strategy"}

configure_logging()
logger = logging.getLogger("quant_backtester.api")


def create_app() -> Flask:
    app = Flask(__name__)

    @app.before_request
    def _start_timer():
        g.request_start = time.monotonic()

    @app.after_request
    def _log_request(response):
        duration_ms = (time.monotonic() - g.request_start) * 1000
        log_event(
            logger, logging.INFO, "http_request",
            method=request.method, path=request.path,
            status=response.status_code, duration_ms=round(duration_ms, 2),
        )
        return response

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/strategies")
    def list_strategies():
        return jsonify({"strategies": available_strategies()})

    @app.post("/backtests")
    def create_backtest():
        payload = request.get_json(force=True, silent=True) or {}
        missing = REQUIRED_FIELDS - payload.keys()
        if missing:
            return jsonify({"error": f"missing required fields: {sorted(missing)}"}), 400

        if payload["strategy"] not in available_strategies():
            return jsonify({"error": f"Unknown strategy '{payload['strategy']}'. Available: {available_strategies()}"}), 400

        run_id = str(uuid.uuid4())
        engine = get_engine()

        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO backtest_runs
                        (id, ticker, strategy, strategy_params, start_date, end_date,
                         initial_cash, cost_bps, status)
                    VALUES
                        (:id, :ticker, :strategy, :params, :start, :end, :cash, :cost_bps, 'pending')
                """),
                {
                    "id": run_id,
                    "ticker": payload["ticker"],
                    "strategy": payload["strategy"],
                    "params": json.dumps(payload.get("strategy_params", {})),
                    "start": payload["start"],
                    "end": payload["end"],
                    "cash": payload.get("initial_cash", 100_000.0),
                    "cost_bps": payload.get("cost_bps", 5.0),
                },
            )

        run_backtest_task.delay(run_id, payload)

        log_event(
            logger, logging.INFO, "backtest_enqueued",
            run_id=run_id, ticker=payload["ticker"], strategy=payload["strategy"],
        )

        return jsonify({"id": run_id, "status": "pending"}), 202

    @app.get("/backtests/<run_id>")
    def get_backtest(run_id: str):
        engine = get_engine()
        with engine.begin() as conn:
            row = conn.execute(
                text("""
                    SELECT id, ticker, strategy, status, result, error, created_at, completed_at
                    FROM backtest_runs WHERE id = :id
                """),
                {"id": run_id},
            ).mappings().first()

        if row is None:
            return jsonify({"error": "not found"}), 404
        return jsonify(dict(row))

    @app.get("/backtests")
    def list_backtests():
        engine = get_engine()
        with engine.begin() as conn:
            rows = conn.execute(
                text("""
                    SELECT id, ticker, strategy, status, created_at, completed_at
                    FROM backtest_runs ORDER BY created_at DESC LIMIT 50
                """)
            ).mappings().all()
        return jsonify([dict(r) for r in rows])

    return app


app = create_app()
