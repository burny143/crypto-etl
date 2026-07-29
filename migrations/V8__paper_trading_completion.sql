-- V8: Complete paper trading schema — add missing columns + signals table
-- Run this in Supabase SQL Editor after V2 and V4

-- =============================================================================
-- 1. paper_orders — add decision_key, strategy_id, signal_timestamp, fee
-- =============================================================================
ALTER TABLE paper_orders
    ADD COLUMN IF NOT EXISTS decision_key TEXT,
    ADD COLUMN IF NOT EXISTS strategy_id  TEXT,
    ADD COLUMN IF NOT EXISTS signal_timestamp TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS fee DOUBLE PRECISION DEFAULT 0;

-- Unique index for idempotent lookups by decision_key (prevents duplicate orders)
CREATE UNIQUE INDEX IF NOT EXISTS idx_paper_orders_decision_key ON paper_orders (decision_key);

-- =============================================================================
-- 2. paper_positions — add strategy_id, status (session_id already in V7)
-- =============================================================================
ALTER TABLE paper_positions
    ADD COLUMN IF NOT EXISTS strategy_id TEXT,
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed'));

-- Index for filtering open positions
CREATE INDEX IF NOT EXISTS idx_paper_positions_status ON paper_positions (status);

-- =============================================================================
-- 3. paper_signals — new table for strategy signal persistence
-- =============================================================================
CREATE TABLE IF NOT EXISTS paper_signals (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('hold', 'enter_long', 'enter_short', 'exit_long', 'exit_short')),
    confidence DOUBLE PRECISION NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    candle_timestamp TIMESTAMPTZ NOT NULL,
    decision_key TEXT NOT NULL,
    params JSONB DEFAULT '{}',
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_paper_signals_symbol_tf ON paper_signals (symbol, timeframe);
CREATE INDEX IF NOT EXISTS idx_paper_signals_strategy ON paper_signals (strategy_id);
CREATE INDEX IF NOT EXISTS idx_paper_signals_decision_key ON paper_signals (decision_key);
CREATE INDEX IF NOT EXISTS idx_paper_signals_candle_ts ON paper_signals (candle_timestamp DESC);

-- Unique constraint for idempotent signal recording
CREATE UNIQUE INDEX IF NOT EXISTS idx_paper_signals_unique
    ON paper_signals (decision_key);

-- =============================================================================
-- 4. RLS policies for paper_signals (anon can insert/select)
-- =============================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'paper_signals' AND policyname = 'Allow anon insert signals') THEN
        CREATE POLICY "Allow anon insert signals" ON paper_signals FOR INSERT TO anon WITH CHECK (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'paper_signals' AND policyname = 'Allow anon select signals') THEN
        CREATE POLICY "Allow anon select signals" ON paper_signals FOR SELECT TO anon USING (true);
    END IF;
END
$$;

-- =============================================================================
-- 5. RLS policies for paper_equity_curve (anon insert/select) — missing from V4
-- =============================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'paper_equity_curve' AND policyname = 'Allow anon insert equity') THEN
        CREATE POLICY "Allow anon insert equity" ON paper_equity_curve FOR INSERT TO anon WITH CHECK (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'paper_equity_curve' AND policyname = 'Allow anon select equity') THEN
        CREATE POLICY "Allow anon select equity" ON paper_equity_curve FOR SELECT TO anon USING (true);
    END IF;
END
$$;