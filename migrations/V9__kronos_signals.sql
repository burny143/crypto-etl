-- =============================================================================
-- V9: Kronos + Trend composite signal tables
-- =============================================================================
-- Precomputed walk-forward Kronos predictions + composite buy/sell signals.
--
-- Written by kronos_signal_etl.py (service_role), read by the browser via
-- the anon key (RLS SELECT policies below). Every row carries the honesty
-- metrics for its symbol/timeframe so the UI can show — even when there is
-- no edge — what the walk-forward evaluation actually measured.
--
-- Signal rule (kept in kronos_signal_etl.py derive_composite_signals):
--   LONG  when close > SMA(50) AND ensemble_vote > 0
--   FLAT  otherwise
-- where ensemble_vote = sign(kronos_sign + linear_sign), walk-forward.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. kronos_predictions — one row per (symbol, timeframe, bar_timestamp)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS kronos_predictions (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    bar_timestamp TIMESTAMPTZ NOT NULL,
    predicted_close DOUBLE PRECISION,
    sma50 DOUBLE PRECISION,
    ensemble_vote DOUBLE PRECISION,          -- sign(kronos + linear); 0 = tie
    model_used TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Lookup + idempotent upsert
CREATE UNIQUE INDEX IF NOT EXISTS idx_kronos_predictions_unique
    ON kronos_predictions (symbol, timeframe, bar_timestamp);
CREATE INDEX IF NOT EXISTS idx_kronos_predictions_ts
    ON kronos_predictions (bar_timestamp DESC);

-- ---------------------------------------------------------------------------
-- 2. kronos_signals — one row per (symbol, timeframe, bar_timestamp)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS kronos_signals (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    bar_timestamp TIMESTAMPTZ NOT NULL,
    signal TEXT NOT NULL CHECK (signal IN ('buy', 'sell', 'flat')),
    reason TEXT,                             -- machine-readable rule trigger
    model_used TEXT,
    -- Walk-forward honesty metrics for the evaluated range (same per run):
    net_return_pct DOUBLE PRECISION,         -- long/flat equity, 0.1% fee/side
    buy_hold_pct DOUBLE PRECISION,           -- buy-and-hold over same bars
    directional_accuracy_pct DOUBLE PRECISION, -- sign(vote)==actual move share
    evaluated_from TIMESTAMPTZ,
    evaluated_to TIMESTAMPTZ,
    evaluated_bars INTEGER,                    -- bars actually evaluated
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Lookup + idempotent upsert
CREATE UNIQUE INDEX IF NOT EXISTS idx_kronos_signals_unique
    ON kronos_signals (symbol, timeframe, bar_timestamp);
CREATE INDEX IF NOT EXISTS idx_kronos_signals_ts
    ON kronos_signals (bar_timestamp DESC);

-- ---------------------------------------------------------------------------
-- 3. RLS — anon can read (browser), service_role can write (ETL)
-- ---------------------------------------------------------------------------
ALTER TABLE kronos_predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE kronos_signals ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'kronos_predictions' AND policyname = 'Allow public read kronos_predictions') THEN
        CREATE POLICY "Allow public read kronos_predictions" ON kronos_predictions FOR SELECT USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'kronos_predictions' AND policyname = 'Allow service all kronos_predictions') THEN
        CREATE POLICY "Allow service all kronos_predictions" ON kronos_predictions FOR ALL TO service_role USING (true) WITH CHECK (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'kronos_signals' AND policyname = 'Allow public read kronos_signals') THEN
        CREATE POLICY "Allow public read kronos_signals" ON kronos_signals FOR SELECT USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'kronos_signals' AND policyname = 'Allow service all kronos_signals') THEN
        CREATE POLICY "Allow service all kronos_signals" ON kronos_signals FOR ALL TO service_role USING (true) WITH CHECK (true);
    END IF;
END
$$;