# Strategy Lifecycle

## Purpose

Define the lifecycle states for a strategy from ideation to active paper trading. This documents the intended workflow, even though parts of it are not yet implemented in the UI.

---

## Lifecycle States

```
                    ┌──────────┐
                    │  DRAFT   │  ← New strategy idea, parameters not yet defined
                    └────┬─────┘
                         │
                         ▼
                    ┌──────────┐
                    │RESEARCHING│  ← Parameter sweeps running, results accumulating
                    └────┬─────┘
                         │
                         ▼
                    ┌──────────┐
                    │ CANDIDATE│  ← Passed initial screening, meets minimum metrics
                    └────┬─────┘
                         │
                         ▼
                 ┌──────────────┐
                 │PAPER_APPROVED│  ← Approved for paper trading
                 └──────┬───────┘
                        │
                        ▼
                 ┌──────────────┐
                 │ ACTIVE_PAPER │  ← Currently being paper traded
                 └──────┬───────┘
                        │
              ┌─────────┴──────────┐
              │                    │
              ▼                    ▼
       ┌──────────┐         ┌──────────┐
       │  PAUSED  │         │ RETIRED  │  ← No longer valid
       └──────────┘         └──────────┘
              │
              │ (may resume)
              ▼
       ┌──────────────┐
       │ ACTIVE_PAPER │  ← If paused strategy is reinstated
       └──────────────┘
```

Additionally, at any point:

```
 ANY STATE ────→ REJECTED  ← Failed validation, insufficient metrics, or design flaw
```

## State Definitions

| State | Meaning | Actions Allowed |
|-------|---------|-----------------|
| **DRAFT** | Initial idea, no research run yet | Edit parameters, define entry/exit rules |
| **RESEARCHING** | Research sweep in progress | View intermediate results, stop run |
| **CANDIDATE** | Passed initial screening | Review metrics, approve or reject for paper trading |
| **PAPER_APPROVED** | Approved for paper trading | Set up paper portfolio allocation, activate |
| **ACTIVE_PAPER** | Currently paper trading | View live P&L, pause, retry, or retire |
| **PAUSED** | Paper trading temporarily stopped | Resume or retire |
| **RETIRED** | Strategy retired (permanently) | Archive results, no further trading |
| **REJECTED** | Failed validation at any stage | Archive with rejection reason |

## Transition Criteria

### DRAFT → RESEARCHING
- Strategy name, indicator, and parameters defined
- Symbol and timeframe selected
- Minimum data available for the selected timeframe

### RESEARCHING → CANDIDATE
- Walk-forward validation completed
- Out-of-sample Sharpe ratio >= 1.0 (minimum threshold)
- Trade count >= 5 (current minimum in `loadStrategyResults()`)
- Maximum drawdown < 50%

### CANDIDATE → PAPER_APPROVED
- Manual review of strategy logic (no look-ahead bias)
- Manual review of parameter reasonableness (no overfitting)
- OOS performance is within 30% of IS performance (no massive decay)
- Strategy is non-obvious (not just "buy low, sell high" on a trending asset)

### PAPER_APPROVED → ACTIVE_PAPER
- Paper portfolio has available cash
- No conflicting active strategy on the same symbol/timeframe

### ACTIVE_PAPER → PAUSED
- Manual pause requested
- Max drawdown exceeds configured threshold (e.g., 30%) in paper trading

### ACTIVE_PAPER / PAUSED → RETIRED
- Consecutive negative months in paper trading
- Strategy decay detected (Sharpe declining over 3+ evaluation periods)
- Better strategy supersedes this one

## Current Implementation Status

| Lifecycle Feature | Status |
|-------------------|--------|
| State machine defined | ✅ This document |
| Strategy definitions table | ❌ Not implemented |
| Approval workflow | ❌ Not implemented |
| Paper trading link to strategy | ❌ Not implemented |
| Strategy health tracking | ❌ Not implemented |
| Strategy retirement | ❌ Not implemented |

Currently, all strategies implicitly start as RESEARCHING when `strategy_research.py` runs, become CANDIDATE if they appear in the Top Strategies panel (Sharpe-ranked, trade_count >= 5), and can be applied to the chart. There is no formal approval or persistence of lifecycle state.
