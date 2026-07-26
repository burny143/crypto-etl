-- =============================================================================
-- V5: Strategy Research Results
-- =============================================================================
-- Stores results from automated strategy research sweeps. Each row is one
-- strategy variant (one parameter combination) tested on one symbol+timeframe.
-- Run ID groups results from a single sweep run.
-- =============================================================================

-- Research runs metadata
CREATE TABLE IF NOT EXISTS research_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    symbols TEXT[] NOT NULL,
    timeframes TEXT[] NOT NULL,
    total_variants INTEGER NOT NULL DEFAULT 0,
    duration_seconds DOUBLE PRECISION,
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed')),
    notes TEXT
);

-- Individual strategy test results
CREATE TABLE IF NOT EXISTS strategy_results (
    id BIGSERIAL PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES research_runs(run_id) ON DELETE CASCADE,
    strategy_name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    params JSONB NOT NULL,
    total_return_pct DOUBLE PRECISION,
    sharpe_ratio DOUBLE PRECISION,
    max_drawdown_pct DOUBLE PRECISION,
    win_rate DOUBLE PRECISION,
    profit_factor DOUBLE PRECISION,
    trade_count INTEGER,
    avg_bars_held DOUBLE PRECISION,
    calmar_ratio DOUBLE PRECISION,
    data_start_date DATE,
    data_end_date DATE,
    data_bar_count INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_strat_results_run ON strategy_results (run_id);
CREATE INDEX IF NOT EXISTS idx_strat_results_lookup ON strategy_results (strategy_name, symbol, timeframe);
CREATE INDEX IF NOT EXISTS idx_strat_results_sharpe ON strategy_results (sharpe_ratio DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_strat_results_created ON strategy_results (created_at DESC);

-- Enable RLS (read-only for anon, so the frontend can display results)
ALTER TABLE research_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE strategy_results ENABLE ROW LEVEL SECURITY;

-- Public SELECT policies
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'research_runs' AND policyname = 'Allow public read research_runs') THEN
        CREATE POLICY "Allow public read research_runs" ON research_runs FOR SELECT USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'strategy_results' AND policyname = 'Allow public read strategy_results') THEN
        CREATE POLICY "Allow public read strategy_results" ON strategy_results FOR SELECT USING (true);
    END IF;
END
$$;

-- Allow service_role (our ETL) full access
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'research_runs' AND policyname = 'Allow service all research_runs') THEN
        CREATE POLICY "Allow service all research_runs" ON research_runs FOR ALL TO service_role USING (true) WITH CHECK (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'strategy_results' AND policyname = 'Allow service all strategy_results') THEN
        CREATE POLICY "Allow service all strategy_results" ON strategy_results FOR ALL TO service_role USING (true) WITH CHECK (true);
    END IF;
END
$$;
