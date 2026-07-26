-- =============================================================================
-- V4: Allow anon CRUD on paper trading tables
-- =============================================================================
-- The frontend uses the anon key to place paper trades, manage positions, and
-- record equity snapshots. These policies mirror the existing V3 approach for
-- crypto_research — personal tool, fake money, no need for write restrictions.
-- =============================================================================

-- paper_orders: anon can INSERT (place), UPDATE (cancel/modify), SELECT (view)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'paper_orders' AND policyname = 'Allow anon insert orders') THEN
        CREATE POLICY "Allow anon insert orders" ON paper_orders FOR INSERT TO anon WITH CHECK (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'paper_orders' AND policyname = 'Allow anon update orders') THEN
        CREATE POLICY "Allow anon update orders" ON paper_orders FOR UPDATE TO anon USING (true) WITH CHECK (true);
    END IF;
END
$$;

-- paper_positions: anon can INSERT (open), UPDATE (modify pnl/close), DELETE (force close), SELECT (view)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'paper_positions' AND policyname = 'Allow anon insert positions') THEN
        CREATE POLICY "Allow anon insert positions" ON paper_positions FOR INSERT TO anon WITH CHECK (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'paper_positions' AND policyname = 'Allow anon update positions') THEN
        CREATE POLICY "Allow anon update positions" ON paper_positions FOR UPDATE TO anon USING (true) WITH CHECK (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'paper_positions' AND policyname = 'Allow anon delete positions') THEN
        CREATE POLICY "Allow anon delete positions" ON paper_positions FOR DELETE TO anon USING (true);
    END IF;
END
$$;

-- paper_equity_curve: anon can INSERT (record snapshot), SELECT (view history)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'paper_equity_curve' AND policyname = 'Allow anon insert equity') THEN
        CREATE POLICY "Allow anon insert equity" ON paper_equity_curve FOR INSERT TO anon WITH CHECK (true);
    END IF;
END
$$;
