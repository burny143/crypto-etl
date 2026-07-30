# trading-research — Monorepo Agent Instructions

## Repository Authority

- **`crypto-etl/`** — Only active product. All development happens here.
- **`vibe-trading/`** — Read-only reference. Never modify, copy from, or depend on it.
- **`.ai/`** — Governance + session state. Contains scope, prohibited actions, financial safety, current milestone, and recovery state files.

## Critical Rules

- `vibe-trading/` is **READ-ONLY** — never create/edit/delete files there
- All new code, frontend changes, DB changes, tools → `crypto-etl/` only
- Backup before edits: `cp file "crypto-etl/.backups/file_underscored.$(date +%s).bak"`
- Never embed `service_role` key in frontend code
- Never hardcode Supabase URLs/keys in production code
- No live trading / broker execution

## Project Structure

```
trading-research/
├── crypto-etl/              # Active product
│   ├── bot/                 # Paper-trading bot (Python)
│   │   ├── pyproject.toml   # Deps, pytest, ruff, black, mypy config
│   │   ├── strategies/      # Strategy implementations (RSI, Breakout Hunter, etc.)
│   │   ├── tests/           # 157 tests passing
│   │   └── ...              # engine, portfolio, risk, data, execution, domain
│   ├── index.html           # Primary UI (vanilla JS, Lightweight Charts v5)
│   ├── strategy_research.py # 8 strategies, param sweeps, walk-forward backtest
│   ├── historical_etl.py    # OHLCV ETL via CCXT (OKX)
│   ├── etl.py               # Price snapshots (30-min GitHub Actions)
│   ├── migrations/          # SQL migrations V2-V5
│   ├── .github/workflows/   # Automated ETL + research pipelines
│   └── .backups/            # Edit backups (gitignored)
├── vibe-trading/            # Read-only research reference
└── .ai/                     # Governance + session state
```

## How to Run

### Terminal UI (primary)
```powershell
cd crypto-etl
python -m http.server 8080
# Open http://localhost:8080
```

### ETL / Research (require Supabase env vars)
```powershell
cd crypto-etl
$env:SUPABASE_URL="https://ymnlqggxeeyqvrojsrzh.supabase.co"
$env:SUPABASE_SERVICE_ROLE_KEY="<from setup.ps1 line 35>"

python etl.py                    # Current price snapshot
python historical_etl.py         # Historical OHLCV (hours)
python strategy_research.py      # Full sweep (9,437 variants)
```

### Bot Development (Python paper-trading engine)
```powershell
cd crypto-etl/bot
# Install deps (if needed)
pip install -e ".[dev]"

# Run tests
python -m pytest -v --tb=short        # 157 tests, ~1.3s
python -m pytest --cov=bot --cov-report=term  # Coverage (floor 75%)

# Lint / format / typecheck
ruff check .
ruff format --check .
mypy bot/
```

## Bot Architecture (Key Facts)

- **Entry**: `bot/cli.py` → `BotEngine.run_once()` / `run_forever()`
- **Config**: `bot/config.yaml` + env vars (Supabase credentials)
- **Data flow**: `crypto_historical` → validation → `Strategy.evaluate()` → `Signal` → `RiskManager` → `PaperExecutor` → `PortfolioService` → repos → equity snapshot
- **Strategies**: Pure functions `evaluate(candles) -> Signal`. Registered in `StrategyRegistry.register_defaults()` (RSI reversion + Breakout Hunter)
- **Decision keys**: Deterministic SHA256(`strategy_id|symbol|timeframe|candle_ts`) for idempotent orders
- **Money**: `Decimal` everywhere; Supabase stores `DOUBLE PRECISION` (sub-cent loss acceptable)
- **Time**: All timestamps UTC-aware; only completed candles evaluated

## Testing Quirks

- Tests run from `crypto-etl/bot/` (pythonpath `[".."]` in pyproject.toml)
- 157 tests, 88%+ coverage, ruff/black clean, mypy ~12 pre-existing
- No integration tests by default (require Supabase credentials)
- Fixtures: `tests/fixtures/ohlcv_sample.json`, `ohlcv_malformed.json`

## Git Structure

- Root repo tracks `crypto-etl/` as a **gitlink** (submodule-like, no `.gitmodules`)
- Nested repo at `crypto-etl/` has its own `.git` and branch `main`
- After committing in nested repo: `cd .. && git add crypto-etl && git commit -m "update gitlink"`
- Current nested HEAD: `06292df` (parent: `6dd72c8`)

## Supabase Project

- **URL**: `https://ymnlqggxeeyqvrojsrzh.supabase.co`
- **Anon key**: Safe in frontend (RLS restricts to SELECT/INSERT)
- **Service role key**: Backend only (ETL, research, bot) — from env var
- **Tables**: `crypto_historical` (227K OHLCV rows), `crypto_data`, `crypto_research`, `paper_orders`, `paper_positions`, `paper_equity_curve`, `research_runs`, `strategy_results`

## Key Files to Read First

| File | Purpose |
|------|---------|
| `.ai/current-milestone.md` | Active milestone context |
| `.ai/scope.md` | Project boundaries |
| `.ai/prohibited-actions.md` | Hard never-breach rules |
| `.ai/financial-safety.md` | Credential/financial integrity |
| `crypto-etl/bot/ARCHITECTURE.md` | 474-line Phase 0 plan + open questions |
| `crypto-etl/docs/architecture/repository-map.md` | File-by-file map |
| `crypto-etl/docs/data-contracts/` | Strategy, signal, research, portfolio schemas |
| `crypto-etl/docs/decisions/` | ADRs |

## Common Pitfalls

- Confusing "max 3 visible on chart" with limiting indicator catalog
- Treating `vibe-trading/` as writable
- Forgetting to update parent gitlink after nested commits
- Running tests from wrong directory (must be `crypto-etl/bot/`)
- Hardcoding secrets or Supabase URLs

## Mandatory Alignment Guardian

The project defines a read-only alignment review subagent at `.opencode/agents/alignment-guardian.md`. It is the mandatory independent reviewer for the paper-trading bot. The primary implementation agent must invoke the guardian at these checkpoints:

1. **Before the first implementation change** in a new OpenCode session.
2. **After context compaction** or suspected context loss.
3. **After significant architecture or module-boundary changes.**
4. **After changes involving schemas, symbols, timestamps, persistence, idempotency, accounting, risk, or execution.**
5. **Whenever the implementation may have crossed into a later phase.**
6. **Before running the final phase-completion review.**
7. **Before presenting the required final phase report.**
8. **After correcting BLOCKER, HIGH, or required MEDIUM findings.**

### Response Rules

- If the verdict is **ALIGNED**, the main agent may continue only within the current approved phase.
- If the verdict is **CORRECTION REQUIRED**, the main agent must stop new feature development, review the evidence, correct only validated findings within the current phase, run relevant checks, and invoke the guardian again.
- If the verdict is **BLOCKED**, the main agent must stop and request a human decision or missing contract.
- Guardian findings are advisory review findings, not automatic edits. The primary agent must validate each finding against repository evidence before implementing it.
- The guardian may not approve phases. The implementation agent may not approve its own work. Human approval is required before starting another phase.
- No agent may merge or tag without explicit human instruction.

### Invocation

The guardian is a checkpoint-based reviewer, not a background process. Invoke it proactively via OpenCode delegation or an explicit `@alignment-guardian` instruction:

```
@alignment-guardian Perform the mandatory pre-implementation alignment review.
Read the current sources of truth, inspect the current branch and repository
state, do not modify files, return your verdict, and stop.

@alignment-guardian Perform the mandatory pre-completion audit. Review the
current phase scope, git status, git diff, verified contracts, tests,
architecture controls, and the vibe-trading forbidden boundary. Do not modify
anything. Return ALIGNED, CORRECTION REQUIRED, or BLOCKED.
```