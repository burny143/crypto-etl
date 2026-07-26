# Crypto Research Dashboard & Trading Platform

A unified frontend combining **historical crypto OHLCV data** with **AI-powered research**, interactive charting, and paper trading — all built on top of a Supabase-backed ETL pipeline.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                 React SPA (Vite)                     │
│  ┌─────────┐ ┌──────────────────┐ ┌──────────────┐  │
│  │Indicators│ │  Candlestick     │ │Research +    │  │
│  │Controls  │ │  Chart (LC)      │ │Trading Panel │  │
│  └────┬─────┘ └────────┬─────────┘ └──────┬───────┘  │
│       │                │                  │          │
│       ▼                ▼                  ▼          │
│  ┌─────────────────────────────────────────────┐     │
│  │            Supabase Client (anon key)        │     │
│  │  crypto_historical  crypto_research symbols  │     │
│  └─────────────────────┬───────────────────────┘     │
└────────────────────────┼────────────────────────────┘
                         │
              ┌──────────┴──────────┐
              │  FastAPI Backend     │
              │  (port 8765)         │
              │  /api/v1/indicators  │
              │  /api/v1/paper/*     │
              │  /api/v1/research/*  │
              └──────────┬──────────┘
                         │
              ┌──────────┴──────────┐
              │  Supabase (service   │
              │  role key for writes)│
              │  indicators table    │
              │  paper_* tables      │
              └─────────────────────┘
```

## Getting Started

### Prerequisites
- Node.js 18+
- Python 3.11+
- Access to the Supabase project (already configured)

### 1. Database Migration

Run the V2 migration in Supabase SQL Editor to add new tables:
- Open https://supabase.com/dashboard/project/ymnlqggxeeyqvrojsrzh/sql/new
- Copy the contents of `migrations/V2__enhanced_schema.sql`
- Click RUN

### 2. Backend

```powershell
cd crypto-etl/backend
pip install -r requirements.txt

$env:SUPABASE_URL="https://ymnlqggxeeyqvrojsrzh.supabase.co"
$env:SUPABASE_SERVICE_ROLE_KEY="<your-service-role-key>"
$env:CORS_ORIGINS="http://localhost:5173"

uvicorn main:app --reload --port 8765
```

### 3. Frontend

```powershell
cd crypto-etl/frontend
npm install
npm run dev
```

Open http://localhost:5173 in your browser.

### 4. ETL (Data Loading)

```powershell
# Current price snapshots
cd crypto-etl
python etl.py

# Historical OHLCV data (years of data, takes a while)
python historical_etl.py
```

## Project Structure

```
crypto-etl/
├── backend/                    # Python FastAPI service
│   ├── main.py                 # App entry, CORS, routes
│   ├── indicators.py           # Technical indicator computation (SMA, EMA, RSI, MACD, BB, VWAP)
│   ├── paper_trading.py        # Paper trading engine (orders, positions, P&L)
│   ├── research.py             # AI research endpoints + technical analysis
│   └── requirements.txt
├── frontend/                   # React + Vite + TypeScript SPA
│   ├── src/
│   │   ├── App.tsx             # Main layout (3-column: indicators | chart | research+trading)
│   │   ├── main.tsx
│   │   ├── index.css           # Tailwind + custom component classes
│   │   ├── types/index.ts      # TypeScript types + indicator definitions
│   │   ├── lib/
│   │   │   ├── supabase.ts     # Supabase client (anon key, read-only)
│   │   │   └── api.ts          # Backend API client
│   │   ├── stores/
│   │   │   └── tradeStore.ts   # Zustand store (single source of truth)
│   │   └── components/
│   │       ├── layout/TopBar.tsx         # Symbol + timeframe + refresh
│   │       ├── chart/CandlestickChart.tsx # TradingView Lightweight Charts
│   │       ├── research/ResearchPanel.tsx # AI insights + technical analysis
│   │       ├── indicators/IndicatorControls.tsx # Toggle/configure indicators
│   │       └── trading/
│   │           ├── OrderForm.tsx           # Place paper trades
│   │           └── PositionsTable.tsx       # Positions + portfolio summary
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   └── postcss.config.js
├── migrations/
│   └── V2__enhanced_schema.sql # New tables (indicators, paper trading, symbols, ETL metadata)
├── etl.py                       # Current price snapshot ETL (existing)
├── historical_etl.py            # Historical OHLCV ETL (existing)
├── index.html                   # Original dashboard (kept for reference)
├── setup.ps1                    # Supabase setup (existing)
├── supabase_migration.sql       # Base migration (existing)
├── AGENTS.md                    # AI agent conventions
├── .env.example                 # Environment template
└── README.md                    # This file
```

## Database Schema

### Existing Tables (managed by ETL)
| Table | Purpose |
|---|---|
| `crypto_data` | Current price snapshots (updated every few minutes by ETL) |
| `crypto_historical` | OHLCV bars — the primary data source for charts |
| `crypto_research` | AI research entries from the vibe-trading agent |

### New Tables (V2 migration)
| Table | Purpose |
|---|---|
| `symbols` | Symbol registry with display names, sort order, active flag |
| `indicators` | Pre-computed technical indicators (cached, keyed by symbol+tf+name+params) |
| `paper_orders` | Paper trading order history |
| `paper_positions` | Current open positions (one per symbol+side) |
| `paper_equity_curve` | Portfolio value snapshots over time |
| `etl_metadata` | ETL run tracking (earliest/latest bar per symbol+tf) |

### Performance Optimizations
- Indexes on (symbol, timeframe, datetime) for range queries
- Unique constraints on (symbol, timeframe, datetime, indicator_name, param_hash) for idempotent upserts
- RLS policies allow public SELECT on all tables (matching the existing pattern)
- Write access restricted to service_role key (backend-only)

## API Endpoints

All under `http://localhost:8765/api/v1/`:

### Indicators
- `GET /indicators/{symbol}/{timeframe}/{name}?period=20` — Get indicator (cached; add `?force_recompute=true` to recompute)
- `POST /indicators/batch` — Compute multiple indicators at once

### Research
- `GET /research/{symbol}` — Get AI research entries for a symbol
- `GET /research/recent` — Get recent research across all symbols
- `GET /research/analysis/{symbol}/{timeframe}` — Get technical analysis summary

### Paper Trading
- `POST /paper/orders` — Place a market/limit/stop order
- `POST /paper/close` — Close all or part of a position
- `GET /paper/positions` — Get open positions with current P&L
- `GET /paper/orders?symbol=X` — Get order history
- `GET /paper/portfolio` — Get portfolio summary
- `GET /paper/equity` — Get equity curve
- `POST /paper/reset` — Reset paper account

### System
- `GET /health` — Health check

## Key Design Decisions

1. **Charting**: TradingView Lightweight Charts — lightweight, canvas-based, handles 500+ bars smoothly
2. **State Management**: Zustand — minimal boilerplate, no providers needed, works well for this scope
3. **Indicator Computation**: Server-side via pandas/numpy with Supabase caching — avoids re-computation on every page load
4. **Data Loading**: Supabase REST queries with ascending/descending order and limit — efficient for range-based chart views
5. **Paper Trading**: Server-side engine with Supabase persistence — P&L calculations are consistent even across page reloads
6. **Research**: Backend generates technical analysis from OHLCV stats; extensible for LLM integration following vibe-trading patterns
7. **No TA-Lib Required**: All indicators implemented in pure pandas/numpy for zero compilation dependencies

## Extending with AI Research (vibe-trading integration)

The research endpoint at `/api/v1/research/analysis/{symbol}/{timeframe}` currently generates analysis from statistical data. To add LLM-powered research:

1. Add an LLM client in `backend/research.py` (OpenAI, Anthropic, or any LangChain-compatible provider)
2. Create a prompt template that feeds OHLCV stats + computed indicators to the LLM
3. Parse the response and store it in the `crypto_research` table
4. The frontend ResearchPanel will automatically display new entries

## Notes

- **vibe-trading/** is never modified — all new code lives in `crypto-etl/`
- The Supabase anon key is embedded in the frontend (safe — RLS restricts to SELECT)
- The service_role key is backend-only
- For production deployment, add authentication and rate limiting to the backend
