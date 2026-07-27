# Target Data Flow (Proposed)

## Goal

Add end-to-end traceability between research strategy definitions, versioned research results, signal events on the chart, and paper trades — without changing the existing runtime code.

## Proposed Additions

### New Tables (Future — Not Implemented)

The following tables are **recommended** for future implementation. They are not created in this documentation phase.

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `strategy_definitions` | Immutable strategy definitions with versioning | `id`, `name`, `version`, `indicator`, `parameters` (JSONB), `created_at` |
| `strategy_approvals` | Approval workflow for strategy versions | `strategy_id`, `version`, `status`, `approved_by`, `approved_at`, `notes` |
| `signal_events` | Individual signal instances on chart bars | `signal_id`, `strategy_id`, `strategy_version`, `research_run_id`, `symbol`, `timeframe`, `candle_timestamp`, `value` [-1,1], `classification`, `reason_codes` |
| `paper_portfolios` | Named paper portfolios (multi-strategy) | `id`, `name`, `cash_balance`, `created_at` |
| `cash_ledger` | Audit trail for cash movements | `portfolio_id`, `timestamp`, `amount`, `reason`, `signal_id` (nullable) |
| `strategy_health` | Tracking indicator effectiveness over time | `strategy_id`, `evaluation_date`, `ic`, `ir`, `sharpe_decay` |
| `data_quality_runs` | ETL data quality monitoring | `run_id`, `table`, `rows_checked`, `null_percent`, `gap_detected`, `passed` |

### New Columns in Existing Tables (Future — Not Implemented)

- `paper_orders`: Add `signal_id` (UUID, nullable) to link orders to signal events
- `paper_positions`: Add `signal_id` (UUID, nullable) to link open positions to signal events

## Target Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        RESEARCH PIPELINE                            │
│                                                                     │
│  strategy_definitions ──▶ strategy_research.py ──▶ strategy_results │
│       (versioned)              │                          │         │
│                                │                   strategy_results  │
│                                │                   includes version │
│                                ▼                          │         │
│                        research_runs                    │         │
│                        (run metadata)                    │         │
│                                                            ▼         │
│                                                   signal_events     │
│                                                   (per-bar signals)  │
└─────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        FRONTEND PIPELINE                            │
│                                                                     │
│  signal_events ──▶ index.html: loadSignalEvents()                  │
│                        │                                            │
│                        ├──▶ chart BUY/SELL markers                  │
│                        │      (linked by signal_id)                 │
│                        │                                            │
│                        └──▶ paper order form                        │
│                              (pre-fills signal_id on trade)         │
│                                                                     │
│  paper_orders ──▶ includes signal_id column                        │
│  paper_positions ──▶ includes signal_id column                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Traceability Chain (Target)

```
strategy_definitions (id=v1, version=2)
    │
    ▼
research_runs (id=run_abc, strategy_id=v1, timestamp)
    │
    ▼
strategy_results (run_id=run_abc, symbol=BTC-USDT, params={...})
    │
    ▼
signal_events (signal_id=sig_xyz, research_run_id=run_abc, 
               strategy_id=v1, candle_timestamp=..., value=0.8)
    │
    ├──▶ chart marker (signal_id=sig_xyz)
    │
    └──▶ paper_order (signal_id=sig_xyz, filled at candle_timestamp)
```

## Migration Path

The implementation should proceed in this order:

1. **Phase 3a (Documentation):** Define all data contracts and ADRs (current phase)
2. **Phase 3b:** Create `strategy_definitions` and `strategy_approvals` tables; add `strategy_id` column to `strategy_results`
3. **Phase 3c:** Add `signal_events` table; wire frontend to load and display signal events as chart markers
4. **Phase 3d:** Add `signal_id` to `paper_orders`; link paper trades to signal events
5. **Phase 4:** Strategy health tracking, cash ledger, data quality monitoring

## Open Questions

1. Should strategy definitions be versioned as new rows (immutable) or updated in place (mutable with version number)? Proposed: immutable rows with `superseded_by` pointer.
2. Should signal events be pre-computed during research sweeps or computed on-demand by the frontend? Proposed: pre-computed during research for performance, cached in Supabase.
3. How should the signal event data contract handle gaps in the research bar range? Proposed: only emit signals for bars that were evaluated during the research run.
