"""Pure backtest execution: fetch data, run the engine, compute metrics.

Deliberately has no DB side effects and no knowledge of Flask or Celery --
it can be called synchronously from a Flask route or from a Celery task
without any change to this function.
"""

from __future__ import annotations

from quant_backtester.api.registry import build_strategy
from quant_backtester.data.loader import fetch_ohlcv
from quant_backtester.engine.backtest import BacktestEngine
from quant_backtester.metrics.metrics import bootstrap_confidence_interval, max_drawdown, sharpe_ratio


def run_backtest(params: dict) -> dict:
    """Execute one backtest and return a JSON-serializable result dict.

    `params` keys: ticker, start, end, strategy, strategy_params (optional),
    initial_cash (optional), cost_bps (optional).
    """
    data = fetch_ohlcv(params["ticker"], params["start"], params["end"])
    if data.empty:
        raise ValueError(f"No data returned for {params['ticker']} between {params['start']} and {params['end']}")

    strategy = build_strategy(params["strategy"], params.get("strategy_params", {}))
    result = BacktestEngine(
        data,
        strategy,
        initial_cash=params.get("initial_cash", 100_000.0),
        cost_bps=params.get("cost_bps", 5.0),
    ).run()

    ci = bootstrap_confidence_interval(result.returns.to_numpy(), n_resamples=1000)

    metrics = {
        "total_return": float(result.equity_curve.iloc[-1] / result.equity_curve.iloc[0] - 1),
        "sharpe_ratio": sharpe_ratio(result.returns),
        "max_drawdown": max_drawdown(result.equity_curve),
        "num_trades": len(result.trades),
        "final_equity": float(result.equity_curve.iloc[-1]),
        "bootstrap_mean_daily_return_95ci": {"lower": ci["lower"], "upper": ci["upper"]},
    }
    equity_curve = [
        {"date": date.strftime("%Y-%m-%d"), "equity": float(value)}
        for date, value in result.equity_curve.items()
    ]

    return {"metrics": metrics, "equity_curve": equity_curve}
