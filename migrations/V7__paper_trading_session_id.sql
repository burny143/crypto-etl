-- V7: Add session_id column to paper trading tables for per-browser scoping
-- Apply this migration in the Supabase SQL editor before session-scoped code queries work.

ALTER TABLE paper_orders    ADD COLUMN IF NOT EXISTS session_id TEXT;
ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS session_id TEXT;

-- Index for faster filtered queries
CREATE INDEX IF NOT EXISTS idx_paper_orders_session    ON paper_orders    (session_id);
CREATE INDEX IF NOT EXISTS idx_paper_positions_session ON paper_positions (session_id);
