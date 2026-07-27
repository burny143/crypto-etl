# crypto-etl — Unified Crypto Research + Trading Terminal

## Repository Authority

- **`crypto-etl/`** is the only active product. All development happens here.
- **`vibe-trading/`** is read-only reference material. Never modify, copy from, or create dependencies to it.
- **`.ai/current-milestone.md`** is the primary anti-drift control — read it before starting any work.
- Before modifying code, read the relevant **data contract** in `crypto-etl/docs/data-contracts/` and **ADR** in `crypto-etl/docs/decisions/`.
- The complete project context lives in `crypto-etl/AGENTS.md` — read that for commands, structure, and pitfalls.

## Critical Rules

- `vibe-trading/` is **READ-ONLY**. Never create, edit, delete, or modify any file inside it.
- You may **read** any file in `vibe-trading/` to understand research logic, prompts, data shapes, or architecture.
- All new code, frontend changes, database changes, and tools go into `crypto-etl/` only.
- **Backup before every edit.** Copy file to `.backups/` with pattern `{path-underscored}.{timestamp}.bak`. The `.backups/` directory is gitignored scratch space.

## Mandatory Workflow

1. Read `.ai/current-milestone.md` for active milestone context
2. Read this file (`crypto-etl/AGENTS.md`) for project-specific commands and data-flow
3. Read relevant data contract(s) in `crypto-etl/docs/data-contracts/`
4. Read relevant ADR(s) in `crypto-etl/docs/decisions/`
5. Make the smallest safe change — no scope creep
6. Backup before every edit (`.backups/` pattern)
7. Run tests or explicitly note absence
8. Review final diff for secrets/scope drift
9. Update `PROJECT_STATUS.md` if capabilities changed

## Forbidden

- ❌ Live trading or broker execution
- ❌ Embedding service_role key in frontend code
- ❌ Fabricating research results or metrics
- ❌ Full rewrites of `index.html`
- ❌ Modifying `vibe-trading/` for any reason
- ❌ Copying files from `vibe-trading/` to `crypto-etl/`

## Detailed Rules

Detailed governance rules are in the monorepo root files:
- `.ai/scope.md` — project boundaries
- `.ai/prohibited-actions.md` — hard never-breach rules
- `.ai/financial-safety.md` — credential and financial integrity rules
- `.ai/reference-policy.md` — vibe-trading reference usage policy
- `.ai/definition-of-done.md` — completion criteria
- `docs/architecture/` — current/target data flow, repository map
- `docs/decisions/` — Architecture Decision Records
- `docs/data-contracts/` — strategy, signal, research, portfolio contracts
- `docs/research/` — strategy lifecycle, validation policy

## Project Structure

**Main working directory**: `/__Projects/AI Projects/trading-research/crypto-etl/`

### Core Components

- **`index.html`** — PRIMARY UI (vanilla HTML/JS, Lightweight Charts)
- **`strategy_research.py`** — Research engine: 8 strategies, param sweeps, backtest
- **`historical_etl.py`** — Historical OHLCV ETL via CCXT (paginated fetch)
- **`etl.py`** — Current price snapshot ETL (30 min schedule)
- **`setup.ps1`** — Supabase setup (keys, env)
- **`strategy_results.csv`** — Latest full sweep output (9,437 variants)
- **`supabase_migration.sql`** — Original full schema
- **`README.md`** — Project documentation
- **`migrations/`** — Migration SQL files (V2-V5)
- **`.github/workflows/`** — Automated ETL pipelines
  - `schedule.yml` — ETL every 30 min
  - `historical_etl.yml` — Daily historical fetch
  - `research.yml` — Weekly strategy research (Monday 06:00 UTC)
- **`frontend/`** — REACT SPA (secondary/defunct — not being developed)
- **`backend/`** — Python FastAPI (abandoned — all logic ported to JS)
- **`.backups/`** — Edit backups (gitignored)

### What's Currently Working

- **`index.html`** is the primary UI — fully functional terminal with:
  - Landing page → Launch Terminal
  - Candlestick chart (Lightweight Charts v5.2.0) with 12+ indicators
  - Pair selector (30 pairs) + timeframe selector (1h/4h/1d)
  - Signal engine (client-side JS) — define conditions, render buy/sell markers
  - AI-style research panel (generates insights from computed indicators)
  - **Paper trading panel** (right sidebar): trade form (qty, long/short), positions list with live P&L (15s refresh), close button, order history, equity header ($10K cash)
  - All indicator computation runs client-side (vanilla JS — no pandas, no server)
- **EVERYTHING in index.html** — no server needed. Just open in browser or serve with `python -m http.server 8080`

### Data Pipeline

- **`historical_etl.py`**: Fetches OHLCV from OKX via CCXT with pagination
- **`etl.py`**: Current price snapshots every 30 min via GitHub Actions
- **`strategy_results.csv`**: Latest strategy research (9,437 variants)

## How to Run

### Terminal UI (no server needed)

```powershell
cd crypto-etl
python -m http.server 8080
# Open http://localhost:8080
```

### ETL Scripts (with environment variables)

```powershell
cd crypto-etl
$env:SUPABASE_URL="https://ymnlqggxeeyqvrojsrzh.supabase.co"
$env:SUPABASE_SERVICE_ROLE_KEY="<key from setup.ps1 line 35>"

# Current price snapshot
python etl.py

# Historical data download
python historical_etl.py

# Strategy research sweep
python strategy_research.py
```

### Component Setup

#### Backend (if needed for development)

```powershell
cd crypto-etl/backend
pip install -r requirements.txt

$env:SUPABASE_URL="https://ymnlqggxeeyqvrojsrzh.supabase.co"
$env:SUPABASE_SERVICE_ROLE_KEY="<your-service-role-key>"
$env:CORS_ORIGINS="http://localhost:5173"

uvicorn main:app --reload --port 8765
```

#### Frontend (abandoned)

```powershell
cd crypto-etl/frontend
npm install
npm run dev
# Open http://localhost:5173
```

## Database Setup

### Supabase Project

- **URL**: `https://ymnlqggxeeyqvrojsrzh.supabase.co`
- **Anon key**: Embedded in index.html (safe — RLS restricts to SELECT/INSERT)
- **Service role key**: Backend-only (found in `setup.ps1` line 35)

### Migration Steps

1. **Run V2 migration** in Supabase SQL Editor:
   - Open https://supabase.com/dashboard/project/ymnlqggxeeyqvrojsrzh/sql/new
   - Copy `migrations/V2__enhanced_schema.sql`
   - Click RUN

2. **Setup complete with `setup.ps1`**
   - Runs setup: configures Vibe-Trading agent env vars + creates crypto_research table
   - Use verified service_role key (read+write both pass)
   - Use anon key for client-side operations

### Key Tables (queried by index.html)

- `crypto_historical` — OHLCV bars (227,200 rows total)
- `crypto_research` — AI research entries (client-side generated insights)
- `crypto_data` — Current price snapshots
- `paper_orders` — Paper trading orders
- `paper_positions` — Open paper positions
- `paper_equity_curve` — Equity snapshots
- `research_runs` — Strategy research run tracking
- `strategy_results` — Per-variant backtest metrics

### RLS Policies

- `crypto_research`: Public SELECT + anon INSERT (V3)
- `paper_orders`, `paper_positions`, `paper_equity_curve`: Public SELECT + anon INSERT/UPDATE/DELETE (V4)
- `research_runs`, `strategy_results`: Public SELECT, service_role all (V5)

### Supabase Key Usage Rules (do not invent or hard-code keys)

All secrets live in environment variables. Never paste real keys into code, comments, or responses.

| Variable | Type | Where it may be used | Where it must NEVER be used |
|----------|------|----------------------|-----------------------------|
| `NEXT_PUBLIC_SUPABASE_URL` | URL | Client + Server | — |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` (or `SUPABASE_ANON_KEY`) | Publishable / anon | Client-side code, browser, public API routes that rely on RLS | Server-only privileged operations |
| `SUPABASE_SERVICE_ROLE_KEY` | Secret / service_role | Server-only (API routes, server actions, Edge Functions, backend scripts, admin tasks) | Client-side, browser, any public bundle, any code that can reach the user |

**Rules the agent must follow**

1. **Client components / browser code** — Use only `createBrowserClient` / `createClient` with `process.env.NEXT_PUBLIC_SUPABASE_URL` + `process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY`. Rely on Row Level Security (RLS). Never import or reference the service_role key.

2. **Server components, Route Handlers, Server Actions, backend scripts** — For normal user-scoped work prefer the anon key + user's JWT / cookies (so RLS still applies). Only when you truly need to bypass RLS (admin, migrations, webhooks, background jobs) use the service_role key on the **server**.

3. **Never** — Hard-code any key. Put `SUPABASE_SERVICE_ROLE_KEY` in any file that can be shipped to the browser. Log, print, or return the service_role key. Use the service_role key "just to make it work" when the anon key + proper RLS would suffice.

4. **When creating clients** — Browser: `@supabase/ssr` `createBrowserClient` or the official browser client with the public URL + anon key. Server: `@supabase/ssr` `createServerClient` (with cookies) or a plain server client that reads the correct env vars. Admin / bypass-RLS: a separate server-only client that uses the service_role key.

5. **If a key is missing** — Tell the user which env var is required and stop. Do not invent placeholder keys or fall back to the wrong key.

6. **RLS first** — Prefer designing tables + policies so the anon key works. Reach for the service_role key only when the requirement is explicitly "bypass RLS / act as admin".

## Git Conventions

### Commit Workflow

- **Always use git add + git commit for meaningful changes**
- **Push after commits**
- **Backup before every edit** with .backups/ pattern
- **Never modify `vibe-trading/`** for any reason — it's read-only

### Branch Strategy

- Main branch contains deployed production state
- Feature work done in feature branches
- Do NOT force push or rewrite history (unless explicitly requested)

## File Editing Rules

### Backup System

**Before every edit:**

```powershell
# Backup file to .backups/ with timestamp and sanitized path
copy "original-file.js" ".backups\original-file.{timestamp}.bak"
```

- Pattern: `{original-path-underscored}.{timestamp}.bak`
- The `.backups/` directory is gitignored scratch space
- Used only for recovery, never commited

### Do NOT Edit

- **Do NOT edit `vibe-trading/` files** (always read-only)
- **Do NOT copy files from `vibe-trading/` to `crypto-etl/`**
- All new development in `crypto-etl/` only

## Architecture Notes

### Data Flow

1. **Historical data**: `historical_etl.py` → Supabase `crypto_historical`
2. **Current prices**: `etl.py` → Supabase `crypto_data` (30 min schedule)
3. **Strategy research**: `strategy_research.py` → Supabase + CSV export
4. **Research insights**: Client-side JS in index.html → Supabase `crypto_research`
5. **Paper trading**: Client-side JS in index.html → Supabase paper_* tables

### Key Design Decisions

1. **Charting**: TradingView Lightweight Charts canvas-based, handles large datasets efficiently
2. **Indicators**: All client-side in vanilla JS (12 types). No server dependency
3. **Data Loading**: Single query from `crypto_historical` — loads all bars for current symbol/timeframe
4. **Research**: Client-side JS generates insights from indicators
5. **Paper Trading**: Client-side JS → Supabase anon key operations
6. **Max 3 on chart**: Limit applies to chart overlays only. Indicator catalog should keep growing
7. **crypto-etl is the truth**: The React frontend/backend are abandoned

## CI/CD Workflows

### GitHub Actions

All workflows run on `ubuntu-latest` with explicit dependencies:

#### `schedule.yml` (price snapshots)
- Cron: `*/30 * * * *` (every 30 minutes)
- Dependencies: yfinance, supabase, ccxt

#### `historical_etl.yml` (daily historical data)
- Cron: `5 0 * * *` (00:05 UTC)
- Dependencies: yfinance, supabase, pandas, ccxt

#### `research.yml` (weekly strategy research)
- Cron: `0 6 * * 1` (06:00 UTC Monday)
- Dependencies: pandas, numpy, supabase

### Workflow Patterns

1. **Setup**: actions/checkout → actions/setup-python
2. **Install**: pip install with exact dependencies
3. **Environment**: Set SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY
4. **Execution**: Run appropriate Python script
5. **Artifacts**: Upload results (CSV files)

## Commonly Needed Commands

### Run Full ETL Pipeline (local)

```powershell
cd crypto-etl
$env:SUPABASE_URL="https://ymnlqggxeeyqvrojsrzh.supabase.co"
$env:SUPABASE_SERVICE_ROLE_KEY="<key>"

# Current prices (every 30 min)
python etl.py

# Historical data (daily, hours long)
python historical_etl.py

# Strategy research (weekly, many variants)
python strategy_research.py --export strategy_results.csv
```

### For Development

```powershell
# Serve UI locally
cd crypto-etl
python -m http.server 8080

# Local development (frontend abandoned, keep backend only if needed)
cd crypto-etl/backend
uvicorn main:app --reload --port 8765
```

### Database Validation

```powershell
# Test Supabase connectivity
# Using setup.ps1 validates:
# 1. Service role key works (read+write)
# 2. Crypto_research table exists or creates it
# 3. Crypto_data accessible
```

## Common Pitfalls

### Avoid These Mistakes

- **Don't modify `vibe-trading/`** (ever, even for reading reference)
- **Don't add features that don't serve the research workflow**
- **Always read `crypto-etl/AGENTS.md` first** when starting fresh
- **Don't forget to read the relevant data contract and ADR** before modifying code that touches data shapes or architecture
- **Don't confuse "max 3 visible on chart" with limiting the indicator catalog**
- **Never embed service_role key in frontend code**
- **Never hardcode Supabase URLs/keys in production code**
- **Don't check `PROJECT_STATUS.md` at the end of every task** — update it if capabilities changed

### Testing Considerations

- **Strategy sweep takes hours** (9,437 variants × 10 symbols × 2 timeframes)
- **Historical ETL can take days** (years of data)
- **Current price updates** every 30 minutes
- **Paper trading resets** on page reload (no persistent cash balance)

## Next Unfinished Items

See also `ROADMAP.md` for full phased roadmap.

1. **Research-to-chart vertical slice** (CURRENT): Document and prepare traceability from strategy results to chart markers — data contracts, signal events, strategy lifecycle
2. **Widen research sweep**: Run on all 30 symbols + 1h timeframe + wider parameter grids
3. **Walk-forward validation**: Split data into train/test periods (partially done, needs UI wiring)
4. **Wire research into UI**: Show top strategies, overlay signals on chart, one-click paper trade adoption
5. **Strategy decay tracking**: Compare live paper trade performance against research predictions
6. **Portfolio backtester**: Multi-symbol allocation across strategies
7. **Paginated data loading**: Load bars in pages (500 at a time)
8. **Persist cash balance**: Store equity curve properly

## Important Files (quick reference)

- **Primary UI**: `index.html`
- **Research engine**: `strategy_research.py`
- **Current data**: `etl.py`
- **Historical data**: `historical_etl.py`
- **DB schema**: `supabase_migration.sql`
- **Migrations**: `migrations/` directory
- **Setup**: `setup.ps1`
- **Backups**: `.backups/` directory
- **Governance -- root**: `CLAUDE.md`, `AGENTS.md`, `.ai/`, `PROJECT_STATUS.md`, `ROADMAP.md`
- **Architecture docs**: `docs/architecture/`
- **ADRs**: `docs/decisions/`
- **Data contracts**: `docs/data-contracts/`
- **Research methodology**: `docs/research/`

**Remember**: `crypto-etl/` is the only directory you should modify. `vibe-trading/` is pure reference material.
