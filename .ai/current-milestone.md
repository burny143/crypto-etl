# Current Milestone: Research-to-Chart Vertical Slice

**Status:** Documentation & preparation phase (no runtime code changes)

## Objective

Establish end-to-end traceability from a research strategy result to chart BUY/SELL markers, demonstrating that every signal on the chart can be linked back to a specific, versioned research result.

## Scope

- **Symbol:** BTC/USDT
- **Timeframe:** 4h
- **Strategy:** One existing transparent strategy from the 8-templates set (e.g., RSI Mean Reversion or MACD Crossover)
- **Artifacts:**
  - One versioned research result (walk-forward validated)
  - One signal-event contract instance
  - Chart BUY/SELL markers linked to research evidence
  - Optional paper order linked by signal identifier

## Acceptance Criteria

1. Strategy definition data contract (`crypto-etl/docs/data-contracts/strategy-definition.md`) captures symbol, timeframe, indicator name, parameters, and validation split.
2. Research result data contract (`crypto-etl/docs/data-contracts/research-result.md`) captures the output of a strategy research run with versioning.
3. Signal-event data contract (`crypto-etl/docs/data-contracts/signal-event.md`) defines the traceability chain: signal_id → strategy_id → research_run_id → chart markers.
4. Current data flow is documented, including where traceability is currently lost between strategy_results and chart markers.
5. The gap analysis identifies what tables, columns, or code changes would be needed to close the traceability gap (but does not implement them).
6. The strategy lifecycle (DRAFT → RESEARCHING → CANDIDATE → PAPER_APPROVED → ACTIVE_PAPER → PAUSED/RETIRED/REJECTED) is defined.

## What We Are NOT Doing in This Milestone

- Writing runtime code, SQL migrations, or Supabase schema changes
- Restructuring index.html or extracting modules
- Adding new strategies, indicators, or UI components
- Database migrations or RLS policy changes

## Key Documents

| Document | Purpose |
|----------|---------|
| `docs/data-contracts/strategy-definition.md` | Strategy definition schema and lifecycle |
| `docs/data-contracts/research-result.md` | Versioned research output format |
| `docs/data-contracts/signal-event.md` | Signal traceability contract |
| `docs/data-contracts/paper-portfolio.md` | Paper trading data contract |
| `docs/research/strategy-lifecycle.md` | Strategy lifecycle state machine |
| `docs/research/validation-policy.md` | Walk-forward validation rules |
| `docs/architecture/current-data-flow.md` | Today's data flow with gap analysis |
| `docs/architecture/target-data-flow.md` | Proposed traceable data flow |
| `docs/architecture/repository-map.md` | File-by-file map |
