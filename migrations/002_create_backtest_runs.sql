CREATE TABLE IF NOT EXISTS backtest_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker TEXT NOT NULL,
    strategy TEXT NOT NULL,
    strategy_params JSONB NOT NULL DEFAULT '{}'::jsonb,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    initial_cash DOUBLE PRECISION NOT NULL,
    cost_bps DOUBLE PRECISION NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    result JSONB,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_backtest_runs_created_at ON backtest_runs (created_at DESC);
