"""Flask REST API for running backtests and reading back results.

Synchronous for now: POST /backtests blocks until the backtest finishes,
which is fine for a request that takes a few hundred milliseconds against
a couple hundred bars, and is exactly the problem Day 11 exists to fix
once backtests take minutes over years of data.
"""

from __future__ import annotations

import json
import uuid

from flask import Flask, jsonify, request
from sqlalchemy import text

from quant_backtester.api.registry import available_strategies
from quant_backtester.api.runner import run_backtest
from quant_backtester.data.loader import get_engine

REQUIRED_FIELDS = {"ticker", "start", "end", "strategy"}


def create_app() -> Flask:
    app = Flask(__name__)

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

        run_id = str(uuid.uuid4())
        engine = get_engine()

        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO backtest_runs
                        (id, ticker, strategy, strategy_params, start_date, end_date,
                         initial_cash, cost_bps, status)
                    VALUES
                        (:id, :ticker, :strategy, :params, :start, :end, :cash, :cost_bps, 'running')
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

        try:
            result = run_backtest(payload)
        except Exception as exc:
            with engine.begin() as conn:
                conn.execute(
                    text("""
                        UPDATE backtest_runs SET status = 'failed', error = :err, completed_at = now()
                        WHERE id = :id
                    """),
                    {"err": str(exc), "id": run_id},
                )
            return jsonify({"id": run_id, "status": "failed", "error": str(exc)}), 400

        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE backtest_runs SET status = 'completed', result = :result, completed_at = now()
                    WHERE id = :id
                """),
                {"result": json.dumps(result), "id": run_id},
            )

        return jsonify({"id": run_id, "status": "completed", **result}), 201

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
