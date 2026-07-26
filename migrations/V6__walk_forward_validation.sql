-- =============================================================================
-- V6: Walk-Forward Validation Columns
-- =============================================================================
-- Adds columns to support walk-forward (train/test split) validation in
-- strategy research. Each row gets a 'validation' flag indicating whether
-- the result is in-sample (parameter sweep on training data) or out-of-sample
-- (top params tested on held-out test data).
-- =============================================================================

ALTER TABLE strategy_results
ADD COLUMN IF NOT EXISTS validation TEXT DEFAULT 'in_sample'
CHECK (validation IN ('in_sample', 'out_of_sample'));

ALTER TABLE strategy_results
ADD COLUMN IF NOT EXISTS train_start_date DATE;

ALTER TABLE strategy_results
ADD COLUMN IF NOT EXISTS train_end_date DATE;

ALTER TABLE strategy_results
ADD COLUMN IF NOT EXISTS test_start_date DATE;

ALTER TABLE strategy_results
ADD COLUMN IF NOT EXISTS test_end_date DATE;

-- Add index for querying by validation type
CREATE INDEX IF NOT EXISTS idx_strat_results_validation ON strategy_results (validation);
