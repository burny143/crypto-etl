# Research-to-Chart Vertical Slice Documentation

## Phase 6: Documentation & Preparation

This document provides comprehensive analysis of the current data flow traceability between research results and chart signals in the Crypto Trading Terminal.

### Summary of Findings

#### 1. Current Documentation Status

**Existing Data Contracts:**
- ✅ `docs/data-contracts/strategy-definition.md` - **DRAFT** (83 lines) - Strategy definitions table schema proposed
- ✅ `docs/data-contracts/research-result.md` - **DRAFT** (95 lines) - Research results versioning schema proposed  
- ✅ `docs/data-contracts/signal-event.md` - **DRAFT** (110 lines) - Signal events table schema proposed
- ✅ `docs/data-contracts/paper-portfolio.md` - **DRAFT** (98 lines) - Paper trading contracts

**Architecture Documentation:**
- ✅ `docs/architecture/current-data-flow.md` - **Complete** (222 lines) - Current data flows and gap analysis
- ✅ `docs/architecture/target-data-flow.md` - **Complete** (97 lines) - Proposed future data flows
- ✅ `docs/research/strategy-lifecycle.md` - **Complete** (112 lines) - Strategy lifecycle states and transitions

#### 2. Gap Analysis

**Critical Traceability Gaps:**

**Gap 1: Strategy Results → Chart Markers**
- **Problem:** No stable identifiers linking strategy results to chart markers
- **Current:** `strategy_results` has only `strategy_name` (no `strategy_id` or `strategy_version`)
- **Impact:** Cannot determine which strategy version produced current chart markers

**Gap 2: Research Results → Paper Trades**  
- **Problem:** No link between paper trades and underlying research signals
- **Current:** `paper_orders` and `paper_positions` lack `signal_id` column
- **Impact:** Post-trade attribution impossible

**Gap 3: Strategy Logic Duplication**
- **Problem:** Same indicator logic implemented in Python and JavaScript
- **Current:** `strategy_research.py` vs `index.html` independent implementations
- **Impact:** No automated verification of equivalent behavior

#### 3. Strategy Lifecycle States

**Current Implementation:** All strategies implicitly start as RESEARCHING when `strategy_research.py` runs, become CANDIDATE if they appear in Top Strategies panel (Sharpe-ranked, trade_count >= 5), and can be applied to chart.

**Documented States (from `docs/research/strategy-lifecycle.md`):**
```
DRAFT → RESEARCHING → CANDIDATE → PAPER_APPROVED → ACTIVE_PAPER → (PAUSED | RETIRED)
                     ↓
                  REJECTED (any state)
```

**Transitions Documented:**
- `DRAFT → RESEARCHING`: Parameters defined, data available
- `RESEARCHING → CANDIDATE`: OOS Sharpe >= 1.0, Trade count >= 5, Max drawdown < 50%
- `CANDIDATE → PAPER_APPROVED`: Manual review of strategy logic and parameters
- `PAPER_APPROVED → ACTIVE_PAPER`: Portfolio cash available, no conflicts
- `ACTIVE_PAPER → {PAUSED, REJECTED}`: Manual pause or retirement
- `ANY_STATE → REJECTED`: Failed validation

#### 4. Code Structure Analysis

**Current Working Components:**
1. **Python Backend (`strategy_research.py`)**:
   - 8 strategy templates with parameter grids
   - Walk-forward validation (70/30 split)
   - Produces `strategy_results.csv` and Supabase `strategy_results`
   - Metrics: Sharpe ratio, total return, max drawdown, win rate, profit factor

2. **JavaScript Frontend (`index.html`)**:
   - 12+ technical indicators
   - Signal engine for chart markers
   - Paper trading with order management
   - Supabase anon-key operations

3. **Database Schema:**
   - `crypto_historical`: OHLCV data (~227k rows)
   - `crypto_data`: Current price snapshots
   - `crypto_research`: AI-generated insights
   - `research_runs`: Run metadata
   - `strategy_results`: Backtest metrics (versioned)
   - `paper_orders`, `paper_positions`, `paper_equity_curve`

#### 5. Recommended Documentation Improvements

**All required documentation files already exist. Additional improvements needed:**

1. **Enhanced Current Data Flow Documentation**
   - Add more detailed traceability analysis
   - Include specific code references and line numbers
   - Document migration path from current to target state

2. **Strategy Lifecycle Implementation Status**
   - Clarify current vs proposed lifecycle states
   - Document pending implementation items
   - Add UI workflow documentation

3. **Signal Event Data Contract Refinement**
   - Add constraint details
   - Document validation rules
   - Include migration examples

#### 6. Executive Summary

**Current State:** Comprehensive documentation framework exists but implementation incomplete. Key traceability gaps identified between research results and chart markers, and between research and paper trades.

**Documentation Status:** ✅ **COMPLETE** - All required documentation files exist with detailed schemas and gap analysis

**Remaining Work:**
- Implement `strategy_definitions` and `strategy_approvals` tables
- Add `signal_events` table and wire frontend
- Add `signal_id` to `paper_orders` and `paper_positions`
- Implement strategy health tracking
- Complete cash ledger implementation
