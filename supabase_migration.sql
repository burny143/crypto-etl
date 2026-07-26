-- Run this once in your Supabase SQL Editor to create the research table.
-- The agent writes to this table; the dashboard reads from it.

CREATE TABLE IF NOT EXISTS crypto_research (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    report_type TEXT NOT NULL,       -- 'market_analysis', 'backtest_result', 'signal', 'factor_score', 'news_summary'
    title TEXT NOT NULL,             -- short human-readable title
    summary TEXT NOT NULL,           -- main research text / analysis
    details JSONB DEFAULT '{}',      -- structured data (metrics, scores, config, etc.)
    sentiment TEXT,                  -- 'bullish', 'bearish', 'neutral', or NULL
    confidence REAL,                 -- 0.0 to 1.0, or NULL
    source TEXT DEFAULT 'vibe-trading',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_symbol ON crypto_research(symbol);
CREATE INDEX IF NOT EXISTS idx_research_created ON crypto_research(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_research_type ON crypto_research(report_type);

-- Allow public read access (matching existing dashboard policy)
ALTER TABLE crypto_research ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'crypto_research' AND policyname = 'Allow public read'
    ) THEN
        CREATE POLICY "Allow public read" ON crypto_research FOR SELECT USING (true);
    END IF;
END
$$;
