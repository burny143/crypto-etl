# Roadmap

## Phase 1 — Foundation (COMPLETE)
- [x] Historical OHLCV ETL (CCXT → Supabase)
- [x] Current price snapshot pipeline (30-min GitHub Actions)
- [x] Primary vanilla JS terminal UI (index.html)
- [x] 12+ technical indicators (client-side JS)
- [x] 30 symbols × 3 timeframes in Supabase
- [x] Paper trading with live P&L

## Phase 2 — Strategy Research (COMPLETE)
- [x] Strategy research engine (strategy_research.py)
- [x] 8 strategy templates with parameter sweeps
- [x] Walk-forward validation (70/30 train/test split)
- [x] 9,437 variants tested across top symbols
- [x] Strategy results displayed in UI (Top Strategies panel)

## Phase 3 — Research-to-Chart Traceability (CURRENT MILESTONE)
- [ ] Complete strategy definition data contract
- [ ] Complete signal-event data contract with full traceability
- [ ] Versioned research result linking strategies to chart markers
- [ ] Chart BUY/SELL markers linked to research evidence
- [ ] Optional paper order linked by signal identifier
- [ ] ADR-0006: Plan for incremental index.html modularization

## Phase 4 — Validation & Persistence (NEXT)
- [ ] Walk-forward validation wired fully into UI
- [ ] Strategy decay tracking (compare live paper trade performance vs research predictions)
- [ ] Persist cash balance across page reloads
- [ ] Portfolio backtester (multi-symbol allocation)
- [ ] Paginated data loading (500 bars at a time)

## Phase 5 — Expansion & Optimization (FUTURE)
- [ ] Widen research sweep to all 30 symbols + 1h timeframe
- [ ] Parameter grids with wider ranges
- [ ] Strategy health monitoring (IC/IR tracking over time)
- [ ] Factor decay awareness
- [ ] Regime-aware signal filtering

## Never Planned
- Live trading or broker execution
- Machine learning or reinforcement learning strategies
- React SPA or FastAPI backend development
- LangGraph, MCP, or agent swarm integration
