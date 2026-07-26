-- =============================================================================
-- V2: Enhanced Schema — Indicators, Paper Trading, ETL Metadata
-- =============================================================================
-- Run this in Supabase SQL Editor after the base V1 migration.
-- Adds tables for pre-computed indicators, paper trading, and ETL tracking.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Indicators cache
-- ---------------------------------------------------------------------------
-- Stores pre-computed technical indicator values so the frontend doesn't
-- need to recompute them on every load. Unique on (symbol, timeframe,
-- datetime, indicator_name, parameters) so different parameter sets for
-- the same indicator are stored separately.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS indicators (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    datetime TIMESTAMPTZ NOT NULL,
    indicator_name TEXT NOT NULL,      -- 'sma', 'ema', 'rsi', 'macd', 'bb', 'vwap'
    parameters JSONB NOT NULL DEFAULT '{}',  -- e.g. {"period": 14} or {"fast": 12, "slow": 26}
    value DOUBLE PRECISION,            -- scalar values (SMA, EMA, RSI)
    value_json JSONB,                   -- multi-value indicators (MACD: {macd, signal, hist}, BB: {upper, mid, lower})
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast lookups by symbol + timeframe + indicator
CREATE INDEX IF NOT EXISTS idx_indicators_lookup
    ON indicators (symbol, timeframe, indicator_name, datetime DESC);

-- Unique constraint to allow safe upserts
CREATE UNIQUE INDEX IF NOT EXISTS idx_indicators_unique
    ON indicators (symbol, timeframe, datetime, indicator_name, md5(parameters::text));

-- ---------------------------------------------------------------------------
-- 2. Paper trading — orders
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS paper_orders (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('long', 'short')),
    order_type TEXT NOT NULL DEFAULT 'market' CHECK (order_type IN ('market', 'limit', 'stop')),
    quantity DOUBLE PRECISION NOT NULL,
    price DOUBLE PRECISION,            -- filled price (NULL for pending)
    stop_price DOUBLE PRECISION,       -- for stop orders
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'open', 'filled', 'cancelled', 'rejected')),
    reason TEXT,                        -- rejection reason if any
    opened_at TIMESTAMPTZ DEFAULT NOW(),
    filled_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    pnl DOUBLE PRECISION,              -- realized P&L when closed
    notes TEXT,
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_paper_orders_symbol ON paper_orders (symbol);
CREATE INDEX IF NOT EXISTS idx_paper_orders_status ON paper_orders (status);
CREATE INDEX IF NOT EXISTS idx_paper_orders_created ON paper_orders (opened_at DESC);

-- ---------------------------------------------------------------------------
-- 3. Paper trading — open positions
-- ---------------------------------------------------------------------------
-- A simplified positions table. For a long position: quantity > 0.
-- For a short position: quantity < 0. entry_price is the average entry.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS paper_positions (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('long', 'short')),
    quantity DOUBLE PRECISION NOT NULL,
    entry_price DOUBLE PRECISION NOT NULL,
    current_price DOUBLE PRECISION,
    unrealized_pnl DOUBLE PRECISION,
    realized_pnl DOUBLE PRECISION DEFAULT 0,
    opened_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}',
    UNIQUE (symbol, side)  -- one position per symbol per side
);

CREATE INDEX IF NOT EXISTS idx_paper_positions_active ON paper_positions (symbol);

-- ---------------------------------------------------------------------------
-- 4. Paper trading — equity curve
-- ---------------------------------------------------------------------------
-- Periodic snapshots of total portfolio value for charting.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS paper_equity_curve (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    equity DOUBLE PRECISION NOT NULL,     -- total portfolio value
    cash DOUBLE PRECISION DEFAULT 0,      -- unallocated cash
    margin_used DOUBLE PRECISION DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_equity_timestamp ON paper_equity_curve (timestamp DESC);

-- ---------------------------------------------------------------------------
-- 5. ETL metadata — track what data we've loaded
-- ---------------------------------------------------------------------------
-- Helps the ETL scripts know what time ranges have been fetched, avoiding
-- redundant downloads and supporting incremental updates.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS etl_metadata (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'ccxt',
    earliest_bar TIMESTAMPTZ,
    latest_bar TIMESTAMPTZ,
    total_bars INTEGER DEFAULT 0,
    last_run_at TIMESTAMPTZ DEFAULT NOW(),
    status TEXT DEFAULT 'ok' CHECK (status IN ('ok', 'running', 'error')),
    error_message TEXT,
    UNIQUE (symbol, timeframe, source)
);

-- ---------------------------------------------------------------------------
-- 6. Symbols registry
-- ---------------------------------------------------------------------------
-- Central list of all supported trading pairs with metadata.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS symbols (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL UNIQUE,
    base_asset TEXT NOT NULL,
    quote_asset TEXT NOT NULL DEFAULT 'USDT',
    display_name TEXT,
    exchange TEXT DEFAULT 'okx',
    asset_type TEXT DEFAULT 'spot' CHECK (asset_type IN ('spot', 'perp', 'future')),
    active BOOLEAN DEFAULT TRUE,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Populate symbols from the current ETL list if empty
INSERT INTO symbols (symbol, base_asset, display_name, sort_order)
SELECT s.symbol, s.base, s.display, s.ord
FROM (VALUES
    ('BTC-USDT', 'BTC', 'Bitcoin', 1),
    ('ETH-USDT', 'ETH', 'Ethereum', 2),
    ('XRP-USDT', 'XRP', 'XRP', 3),
    ('SOL-USDT', 'SOL', 'Solana', 4),
    ('BNB-USDT', 'BNB', 'BNB', 5),
    ('ADA-USDT', 'ADA', 'Cardano', 6),
    ('DOGE-USDT', 'DOGE', 'Dogecoin', 7),
    ('AVAX-USDT', 'AVAX', 'Avalanche', 8),
    ('DOT-USDT', 'DOT', 'Polkadot', 9),
    ('LINK-USDT', 'LINK', 'Chainlink', 10),
    ('POL-USDT', 'POL', 'Polygon', 11),
    ('UNI-USDT', 'UNI', 'Uniswap', 12),
    ('SHIB-USDT', 'SHIB', 'Shiba Inu', 13),
    ('LTC-USDT', 'LTC', 'Litecoin', 14),
    ('BCH-USDT', 'BCH', 'Bitcoin Cash', 15),
    ('ATOM-USDT', 'ATOM', 'Cosmos', 16),
    ('ETC-USDT', 'ETC', 'Ethereum Classic', 17),
    ('XLM-USDT', 'XLM', 'Stellar', 18),
    ('FIL-USDT', 'FIL', 'Filecoin', 19),
    ('TRX-USDT', 'TRX', 'TRON', 20),
    ('NEAR-USDT', 'NEAR', 'NEAR Protocol', 21),
    ('APT-USDT', 'APT', 'Aptos', 22),
    ('ARB-USDT', 'ARB', 'Arbitrum', 23),
    ('OP-USDT', 'OP', 'Optimism', 24),
    ('SUI-USDT', 'SUI', 'Sui', 25),
    ('PEPE-USDT', 'PEPE', 'Pepe', 26),
    ('INJ-USDT', 'INJ', 'Injective', 27),
    ('TIA-USDT', 'TIA', 'Celestia', 28),
    ('SEI-USDT', 'SEI', 'Sei', 29),
    ('STRK-USDT', 'STRK', 'StarkNet', 30)
) AS s(symbol, base, display, ord)
WHERE NOT EXISTS (SELECT 1 FROM symbols WHERE symbol = s.symbol)
ON CONFLICT (symbol) DO NOTHING;

-- ---------------------------------------------------------------------------
-- RLS: Allow public read on all new tables; restrict writes to service_role
-- ---------------------------------------------------------------------------
ALTER TABLE indicators ENABLE ROW LEVEL SECURITY;
ALTER TABLE paper_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE paper_positions ENABLE ROW LEVEL SECURITY;
ALTER TABLE paper_equity_curve ENABLE ROW LEVEL SECURITY;
ALTER TABLE etl_metadata ENABLE ROW LEVEL SECURITY;
ALTER TABLE symbols ENABLE ROW LEVEL SECURITY;

-- Public read policies (matching existing pattern on crypto_research)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'indicators' AND policyname = 'Allow public read indicators') THEN
        CREATE POLICY "Allow public read indicators" ON indicators FOR SELECT USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'paper_orders' AND policyname = 'Allow public read orders') THEN
        CREATE POLICY "Allow public read orders" ON paper_orders FOR SELECT USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'paper_positions' AND policyname = 'Allow public read positions') THEN
        CREATE POLICY "Allow public read positions" ON paper_positions FOR SELECT USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'paper_equity_curve' AND policyname = 'Allow public read equity') THEN
        CREATE POLICY "Allow public read equity" ON paper_equity_curve FOR SELECT USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'etl_metadata' AND policyname = 'Allow public read metadata') THEN
        CREATE POLICY "Allow public read metadata" ON etl_metadata FOR SELECT USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'symbols' AND policyname = 'Allow public read symbols') THEN
        CREATE POLICY "Allow public read symbols" ON symbols FOR SELECT USING (true);
    END IF;
END
$$;
