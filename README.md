# Trader's Lab — Crypto Research, Charting, Simulation & Paper Trading Terminal

A complete **client-side vanilla HTML/JS** crypto trading research platform with charting, signal generation, backtesting simulation, paper trading, and a Python research engine — backed by **Supabase** for persistence. No build step, no npm, no framework churn.

---

## Quick Start.

```powershell
cd crypto-etl
python -m http.server 8080
# Open http://localhost:8080
```

**That's it.** Just serve the static files — no `npm install`, no build step, no backend server.

---

## Pages & Features

| Page | File | Description |
|------|------|-------------|
| **Landing** | `index.html` | Entry point with navigation to Charts, Research, and Simulation |
| **Charts** | `charts.html` | Candlestick chart (Lightweight Charts v5), 12+ indicators, signal builder with BUY/SELL markers, paper trading panel (long/short, positions, live P&L, order history) |
| **Research** | `research.html` | Cross-pair sentiment consensus, best strategies per symbol, research history, sortable/expandable results table |
| **Simulation** | `simulation.html` | **Backtesting terminal** — synthetic GBM/GARCH market, 8 strategies, headless batch runner, trade-summary modal on Stop |

---

## The Simulation Terminal (`simulation.html`)

A dedicated **backtesting & simulation environment** built entirely in vanilla JS:

### Core Engine (`js/simulation.js`)

| Component | Description |
|-----------|-------------|
| `SyntheticMarket` | GBM or GARCH(1,1)+t(3) price process; configurable vol, drift, volume coupling; seeded PRNG (mulberry32) |
| `Portfolio` | Cash, positions, fees, running counters (`totalRealizedPnl`, `strategyStats`, `closedTradesCount`, `winningTradesCount`) |
| `SimulationEngine` | Live `_step()` loop + headless `runHeadless()` mode; one-tick execution lag (signals eval on candle N, fill on N+1 open) |
| `StrategyRegistry` | 8 built-in strategies: `breakout_hunter`, `rsi_reversion`, `ema_crossover`, `macd_crossover`, `bollinger_reversion`, `stoch_rsi`, `keltner_breakout`, `rsi_adx_combo`, `rsi_volume_combo`, `buy_and_hold` |

### Execution Model (Realistic)

| Aspect | Implementation |
|--------|----------------|
| **One-tick lag** | Signals evaluated on candle N's close → queued → filled on candle N+1 at its OPEN |
| **Bounded sizing** | Confidence-scaled (5–15% of `initialCash`), capped at 15% equity per position (`computeEntrySize`) |
| **Volume-aware slippage** | `effectiveSlippageBps = base × (1 + k × notional/(volume×price))`, fallback when volume absent |
| **Fee model** | Entry + exit fees as percentage per leg (configurable) |
| **Buy-and-hold baseline** | Incremental O(1) mark-to-market; same one-tick lag & slippage for apples-to-apples comparison |

### Risk-Adjusted Metrics (Headless Output)

| Metric | Description |
|--------|-------------|
| `sortino` | Per-tick Sortino ratio (0% target, downside deviation) |
| `maxDrawdownPct` | Peak-to-trough maximum drawdown |
| `calmarRatio` | Annualized return / max drawdown |
| `unfilledSignals` | Signals queued on final tick with no next bar to fill (diagnostic) |

### UI Features

| Feature | Details |
|---------|---------|
| **Real-time chart** | Lightweight Charts v5, candlesticks + volume, indicator overlays |
| **Strategy selector** | Single strategy or "All" (multi-strategy) mode |
| **Speed control** | 1×–50× tick throttle |
| **Trade-summary modal** | On **Stop**: equity, return %, trades, win rate, net PnL, fees, unrealized, per-strategy breakdown (sorted by PnL) |
| **Modal close** | ✕ button, backdrop click, Escape key |
| **Start button disabled** | While modal is open (prevents new run with stale summary visible) |

---

## Batch Backtester (`js/backtest.js`)

| Capability | Description |
|------------|-------------|
| **`runBatchBacktest({seeds, ticks, realism, randomize})`** | Reuses ONE `SimulationEngine` across all runs (state reset per seed) |
| **Determinism** | Same seed → identical results; `_pendingSignals` cleared per run (no cross-run leak) |
| **Domain randomization** | When `realism: true, randomize: true` — GARCH params jittered per seed (same seed = identical regime) |
| **Walk-forward separation** | In-sample / out-of-sample split supported via `strategy_research.py` |
| **Report** | `formatBatchReport()` — per-seed table + aggregate stats (mean/median/std/p10/p25/p75/p90) + Sortino + CVaR-style tail risk section |

**Recent correctness fixes (2026-07-31):**
- `_pendingSignals` cleared at start **and** end of each `runHeadless()` call — eliminated cross-run signal leak that corrupted batch results
- Hardcoded `10000` literals replaced with `portfolio.initialCash` (equity, return, peak, drawdown)
- WinRate computed from running counters, not UI-capped trades array

---

## Contracts Module (`js/contracts.js`)

Shared TypeScript-like contract definitions for Phase 3 (traceability) and Phase 4 (backtesting):

| Class | Purpose |
|-------|---------|
| `Signal` | Research-generated signal with timestamp, symbol, strategy, direction, strength, price, metadata, signalId |
| `SignalMetadata` | Parameters, indicators, researchId, confidenceFactors, marketData |
| `ConfidenceFactors` | strength, consistency, volume, trend, overall (weighted calculation) |
| `MarketSnapshot` | Price, volume, volatility, liquidity, trend at signal time |
| `BacktestTrade` | Completed trade with exact PnL calculation, fees, slippage, validation |
| `PnLBreakdown` | Gross/net PnL, percentages, entry/exit fees, totalFees, slippageCost, `validateCalculation()` |
| `ResearchResult` | Full strategy run output: runId, strategy, params, symbols, timeframe, IS/OOS PerformanceMetrics, signals, decayRatio, confidenceScore |
| `PerformanceMetrics` | Sharpe, Sortino, Calmar, maxDrawdownPct, winRate, profitFactor, avgTradePnl, tailRatio, painIndex, serenityIndex, `getVolatilityAdjustedReturn()`, `isStatisticallySignificant(confidence)` |
| `ExecutableSignal` | Extends `Signal`; executionPrice, executionFee, `_executed`, `markAsExecuted()`, `isPending()`, `calculateExecutionPnL()` |

**Recent bug fixes (2026-07-31, 15 fixes):**
- CRITICAL: `calculatePnL()` guards against `quantity===0 || entryPrice===0` (no NaN/Infinity)
- CRITICAL: `getVolatilityAdjustedReturn()` uses `Math.abs(maxDrawdownPct)` + explicit zero check (fixes wrong-sign for negative drawdown convention)
- HIGH: `ExecutableSignal` constructor — dead if-block removed; `_executed=true` when both exec params provided; params reordered to mirror `Signal` (signalId after metadata)
- HIGH: `getChartColor/Shape()` throw on unrecognized directions (no silent SELL default)
- HIGH: `isStatisticallySignificant(confidence)` uses confidence-derived z-score thresholds (90%→1.28, 95%→1.645, 99%→2.33)
- HIGH: `formatSummary()` optional-chaining for Sharpe (no TypeError on missing data)
- HIGH: `BacktestTrade` constructor validates `exitTime > entryTime`
- HIGH: Fee-unit mismatch documented (BacktestTrade `fees` = %/leg vs ExecutableSignal `executionFee` = flat currency)
- MEDIUM: Type guards in `formatForChart()`, `toChartMarker()`, `formatForDisplay()`
- LOW: `Math.floor→Math.round` in `toChartMarker()`; expanded `validateCalculation()` (fee consistency); `createdAt` on ExecutableSignal; exports refactored (single source `api` object); `calculatePositionSize()` throws on zero riskAmount

All exports preserved: `Signal, SignalMetadata, ConfidenceFactors, MarketSnapshot, BacktestTrade, PnLBreakdown, ResearchResult, PerformanceMetrics, ExecutableSignal` (accessible as `Contracts.X` or global `X`).

---

## Data Pipeline

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────────────┐
│  CCXT (OKX)     │────▶│  historical_etl.py   │────▶│  Supabase crypto_historical│
│  OHLCV fetch    │     │  (paginated, years)  │     │  ~227k rows, 30 symbols   │
└─────────────────┘     └──────────────────────┘     │  3 timeframes (1h/4h/1d)  │
                                                     └─────────────────────────┘
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────────────┐
│  CCXT (OKX)     │────▶│  etl.py              │────▶│  Supabase crypto_data   │
│  Price snapshots│     │  (every 30 min)      │     │  ~30 rows, current px   │
└─────────────────┘     └──────────────────────┘     └─────────────────────────┘
                                                                     │
                          ┌──────────────────────┐     ┌────────────▼───────────┐
                          │  strategy_research.py│────▶│  Supabase strategy_    │
                          │  8 strategies, walk- │     │  results + research_   │
                          │  forward validation  │     │  runs                  │
                          └──────────────────────┘     └────────────────────────┘
```

### Supabase Tables

| Table | Rows | Purpose | RLS |
|-------|------|---------|-----|
| `crypto_historical` | ~227k | OHLCV bars (30 symbols × 1h/4h/1d) | SELECT (anon) |
| `crypto_data` | ~30 | Current price snapshots (30 min) | SELECT (anon) |
| `crypto_research` | varies | AI research entries (client-generated) | SELECT + INSERT (anon) |
| `research_runs` | per run | Strategy run metadata | SELECT (anon) |
| `strategy_results` | per variant | Per-variant backtest metrics | SELECT (anon) |
| `paper_orders` | per trade | Paper trading order history | SELECT + INSERT/UPDATE/DELETE (anon, session-scoped) |
| `paper_positions` | per position | Open positions, live P&L | SELECT + INSERT/UPDATE/DELETE (anon) |
| `paper_equity_curve` | per snapshot | Portfolio value over time | SELECT + INSERT (anon) |

**All frontend operations use the anon key with RLS.** Service role key is **scripts-only** (ETL, research engine).

---

## Strategy Research Engine (`strategy_research.py`)

| Strategy | Logic |
|----------|-------|
| `rsi_reversion` | Oversold/overbought mean reversion |
| `macd_crossover` | Signal line cross + histogram confirmation |
| `bollinger_reversion` | Touch of lower/upper band |
| `ema_crossover` | Fast/slow EMA cross |
| `stoch_rsi` | K/D cross with overbought/oversold zones |
| `keltner_breakout` | Close above/below KC + volume confirmation |
| `rsi_adx_combo` | Trend strength filter + RSI entries |
| `rsi_volume_combo` | Volume-weighted RSI extremes |
| `buy_and_hold` | Baseline (included in batch, filtered from optimization) |

### Running Research

```powershell
cd crypto-etl
$env:SUPABASE_URL="https://ymnlqggxeeyqvrojsrzh.supabase.co"
$env:SUPABASE_SERVICE_ROLE_KEY="<key>"

# Quick run (smaller param grid, 1-2 min)
python strategy_research.py --quick

# Full sweep (30 symbols × 3 timeframes, wide grids, hours)
python strategy_research.py

# Results → strategy_results.csv + Supabase strategy_results (scoped to run_id)
```

---

## ETL Scripts

```powershell
cd crypto-etl
$env:SUPABASE_URL="https://ymnlqggxeeyqvrojsrzh.supabase.co"
$env:SUPABASE_SERVICE_ROLE_KEY="<key>"

# Current price snapshot (fast, runs every 30 min via GitHub Actions)
python etl.py

# Historical data (slow — years of OHLCV per symbol, paginated CCXT fetch)
python historical_etl.py
```

---

## GitHub Actions CI/CD

| Workflow | Schedule | Purpose |
|----------|----------|---------|
| `schedule.yml` | `*/30 * * * *` | Current price snapshots (`etl.py`) |
| `historical_etl.yml` | `5 0 * * *` | Daily historical OHLCV fetch |
| `research.yml` | `0 6 * * 1` | Weekly strategy research (Monday 06:00 UTC) |

All workflows run on `ubuntu-latest` with explicit dependency installs and artifact uploads.

---

## Project Structure

```
trading-research/
├── crypto-etl/                          # ONLY ACTIVE PRODUCT
│   ├── index.html                       # Landing page
│   ├── charts.html                      # Charting terminal
│   ├── research.html                    # Research dashboard
│   ├── simulation.html                  # Backtesting terminal
│   ├── strategy_research.py             # Strategy engine (8 strategies, WF)
│   ├── etl.py                           # Current price snapshots
│   ├── historical_etl.py                # Historical OHLCV (CCXT)
│   ├── setup.ps1                        # Supabase setup
│   ├── strategy_results.csv             # Latest engine output
│   ├── AGENTS.md                        # AI agent conventions
│   ├── PROJECT_STATUS.md                # Project state & history
│   ├── ROADMAP.md                       # Phased roadmap
│   ├── migrations/                      # SQL migrations (V2–V7)
│   ├── .backups/                        # Edit backups (gitignored)
│   ├── .github/workflows/               # CI/CD
│   ├── js/
│   │   ├── simulation.js                # Simulation engine (core)
│   │   ├── backtest.js                  # Batch backtester
│   │   ├── contracts.js                 # Shared data contracts
│   │   ├── strategies.js                # Signal evaluation fns
│   │   ├── charts.js                    # Charting & indicators
│   │   ├── shared.js                    # Shared utilities
│   ├── docs/
│   │   ├── architecture/                # Data flow diagrams
│   │   ├── data-contracts/              # Research, strategy, signal contracts
│   │   ├── decisions/                   # ADRs
│   │   └── research/                    # Strategy methodology
│   └── .ai/                             # AI governance layer
│       ├── current-milestone.md         # Active milestone
│       ├── scope.md                     # Project boundaries
│       ├── prohibited-actions.md        # Hard rules
│       ├── financial-safety.md          # Credential/financial rules
│       └── reference-policy.md          # vibe-trading usage policy
├── vibe-trading/                        # READ-ONLY reference material
├── .opencode/agents/alignment-guardian.md # AI agent: compliance reviewer
└── PROJECT_STATUS.md                    # Root status (this repo)
```

---

## AI Agent Governance

| File | Purpose |
|------|---------|
| `AGENTS.md` (root) | Overall agent rules, repository authority |
| `crypto-etl/AGENTS.md` | Commands, structure, pitfalls for active product |
| `.ai/current-milestone.md` | Active milestone definition & acceptance criteria |
| `.ai/scope.md` | What this project does/does not build |
| `.ai/prohibited-actions.md` | Hard never-breach rules |
| `.ai/financial-safety.md` | Credential & financial integrity rules |
| `.ai/reference-policy.md` | vibe-trading usage policy |
| `.opencode/agents/alignment-guardian.md` | Read-only compliance reviewer subagent |

**Rule:** `vibe-trading/` is **READ-ONLY**. Never modify, copy from, or depend on it. All development in `crypto-etl/`.

---

## Key Design Decisions (ADR Summary)

| Decision | Rationale |
|----------|-----------|
| Vanilla HTML/JS (no build) | Instant iteration, zero config, deploy anywhere |
| Lightweight Charts (canvas) | Handles 10k+ bars smoothly, no WebGL dependency |
| All indicators client-side | 12+ types in vanilla JS; instant response, no server |
| Supabase anon key + RLS | Safe frontend writes; service role never in browser |
| One-tick execution lag | Signals on candle N close → fill on N+1 open (realistic) |
| Bounded non-compounding sizing | 5–15% of `initialCash`, 15% equity cap (no snowball) |
| Volume-aware slippage | Scales with order size / available volume |
| Walk-forward validation | IS/OOS split prevents lookahead bias |
| Domain randomization (GARCH) | Per-seed regime variation; same seed = identical regime |
| Deterministic PRNG (mulberry32) | Seeded reproducibility for backtests |

---

## Supabase Key Rules

| Key | Type | Where Used |
|-----|------|------------|
| `SUPABASE_URL` | Public URL | Everywhere |
| Anon key | Publishable | Frontend HTML (RLS-protected SELECT/INSERT) |
| Service role key | **Secret** | Python scripts only (ETL, research engine) |

**Never** hard-code service role key in frontend. **Never** log/print it.

---

## Known Issues & Open Items

| Issue | Status | Notes |
|-------|--------|-------|
| GARCH price clamp artifact | Open | Realism mode pins price at 10× floor/ceiling ~1.5–3% ticks; strategies "arbitrage" clamps → inflated alpha. 5-step refactor removed compounding sizing; alpha collapsed from +8912%/+2369% → +444%/+411%. Remaining edge may be genuine or clamp-related. |
| Paper trading cash reset | Unresolved | No persistence to equity curve on reload |
| Strategy→chart traceability | Unresolved | No `signal_id` linking research to chart markers |
| Duplicated strategy/indicator logic | Documented | Python (research) vs JS (chart) — intentional independence |
| No paginated data loading | Unresolved | All bars loaded at once |
| No walk-forward UI | Unresolved | IS/OOS labels exist in data, not wired in UI |

---

## Development Workflow

```powershell
# Serve UI
cd crypto-etl
python -m http.server 8080

# Run ETL (requires Supabase env vars)
$env:SUPABASE_URL="..."
$env:SUPABASE_SERVICE_ROLE_KEY="..."
python etl.py                    # Quick price snapshot
python historical_etl.py         # Full historical (hours)
python strategy_research.py      # Full research sweep (hours)

# Syntax check JS
node --check js/simulation.js
node --check js/contracts.js
node --check js/backtest.js

# Run batch backtest (headless, Node)
node -e "require('./js/backtest.js').runBatchBacktest({seeds:5,ticks:1000})"
```

---

## License

Internal research tooling — not for production trading. All strategies are backtested on synthetic or historical data; past performance ≠ future results.

---

*Last updated: 2026-07-31*  
*See `PROJECT_STATUS.md` for detailed change history and `ROADMAP.md` for phased plan.*