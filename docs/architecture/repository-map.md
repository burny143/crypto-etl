# Repository Map — crypto-etl/

```
crypto-etl/
│
├── index.html                     # PRIMARY UI — 2048-line vanilla JS terminal
│                                    Lightweight Charts v5.2.0, Supabase JS v2
│                                    12 indicators, signal engine, paper trading
│
├── strategy_research.py           # 954-line research engine
│                                    8 strategy templates, walk-forward sweep
│                                    Output: strategy_results.csv + Supabase
│
├── historical_etl.py              # 322-line historical OHLCV fetcher
│                                    CCXT (OKX), 30 symbols × 3 timeframes
│                                    Resampling, batch upserts
│
├── etl.py                         # 159-line price snapshot fetcher
│                                    CCXT with fallback chain, every 30 min
│
├── setup.ps1                      # One-time Supabase setup
│                                    Creates tables, validates keys
│
├── supabase_migration.sql         # V1 base schema (crypto_research)
│
├── strategy_results.csv           # 9,437 strategy variant results
│
├── AGENTS.md                      # Agent conventions, commands, pitfalls
│
├── README.md                      # Project documentation (references React/FastAPI — STALE)
│
├── index_summary.md               # Line-range architectural summary of index.html
│
├── .env.example                   # Environment variable template
│
├── .gitignore                     # Ignores .backups/
│
├── .github/
│   └── workflows/
│       ├── schedule.yml           # Price snapshots every 30 min
│       ├── historical_etl.yml     # Daily historical backfill
│       ├── research.yml           # Weekly strategy research (Mon 06:00 UTC)
│       └── deploy.yml             # GitHub Pages deploy on push to main
│
├── migrations/
│   ├── V2__enhanced_schema.sql    # 6 new tables (indicators, paper, symbols, ETL metadata)
│   ├── V3__research_insert_policy.sql  # Anon INSERT on crypto_research
│   ├── V4__paper_trading_rls.sql      # Anon INSERT/UPDATE/DELETE on paper tables
│   ├── V5__strategy_results.sql        # research_runs + strategy_results tables
│   └── V6__walk_forward_validation.sql # Validation columns for strategy_results
│
├── backend/                       # ABANDONED — Python FastAPI
│   ├── main.py                    #   App entry, CORS, route mounting
│   ├── indicators.py              #   Server-side indicator computation
│   ├── paper_trading.py           #   Paper trading engine
│   ├── research.py                #   Research endpoints
│   ├── signal_engine.py           #   Signal generation
│   └── requirements.txt           #   8 Python dependencies
│
├── frontend/                      # ABANDONED — React 19 + Vite + TypeScript
│   ├── src/
│   │   ├── App.tsx                #   3-column layout
│   │   ├── components/            #   Chart, indicators, research, trading
│   │   ├── stores/                #   Zustand state
│   │   └── lib/                   #   Supabase + API clients
│   └── package.json
│
├── docs/                          # GOVERNANCE DOCUMENTATION (this layer)
│   ├── architecture/
│   │   ├── current-data-flow.md   #   Today's data flow with gap analysis
│   │   ├── target-data-flow.md    #   Proposed traceable data flow
│   │   └── repository-map.md      #   This file
│   ├── decisions/
│   │   ├── ADR-0001-vanilla-js-frontend.md
│   │   ├── ADR-0002-supabase-backend.md
│   │   ├── ADR-0003-vibe-trading-read-only.md
│   │   ├── ADR-0004-paper-trading-only.md
│   │   ├── ADR-0005-transparent-strategies-first.md
│   │   └── ADR-0006-incremental-index-modularization.md
│   ├── data-contracts/
│   │   ├── strategy-definition.md
│   │   ├── research-result.md
│   │   ├── signal-event.md
│   │   └── paper-portfolio.md
│   ├── research/
│   │   ├── strategy-lifecycle.md
│   │   └── validation-policy.md
│   └── reference-adoption/
│       └── README.md
│
└── .backups/                      # Edit backups (gitignored)
```

## Key Architecture Decisions

| Decision | Status | Reference |
|----------|--------|-----------|
| Vanilla JS frontend (no React) | ✅ Active | ADR-0001 |
| Supabase as database + auth | ✅ Active | ADR-0002 |
| vibe-trading as read-only reference | ✅ Active | ADR-0003 |
| Paper trading only (no live) | ✅ Active | ADR-0004 |
| Transparent rule-based strategies | ✅ Active | ADR-0005 |
| Incremental index.html modularization | 📋 Documented | ADR-0006 |

## Undocumented Architecture That Should Be Preserved

1. **Client-side indicator computation** — all 12+ indicators computed in pure JS within `index.html`. No server dependency.
2. **Strategy logic duplication** — Python (`strategy_research.py`) and JavaScript (`index.html`) independently implement the same indicator logic. This is intentional but should be consolidated or cross-tested.
3. **Signal engine flow** — user defines conditions (indicator + comparator + threshold) → `runSignal()` evaluates against `historicalData` → generates `signalChartMarkers[]` → Lightweight Charts renders markers. Conditions are NOT stored in Supabase.
4. **Netting-based paper trading** — opposite-side orders net against existing positions rather than holding both sides simultaneously. Three branches: partial reduction, exact close, exceed opposite.
