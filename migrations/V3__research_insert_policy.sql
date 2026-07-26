-- =============================================================================
-- V3: Allow anon INSERT on crypto_research
-- =============================================================================
-- The frontend uses the anon key (supabase-js client) to write AI-generated
-- research entries. This policy grants INSERT so the Generate button works
-- without needing a backend or service_role key.
-- =============================================================================

-- Allow public (anon) INSERT on crypto_research
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'crypto_research' AND policyname = 'Allow public insert'
    ) THEN
        CREATE POLICY "Allow public insert" ON crypto_research
            FOR INSERT
            TO anon
            WITH CHECK (true);
    END IF;
END
$$;
