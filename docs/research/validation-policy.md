# Validation Policy

## Purpose

Define the rules for validating strategy research results, distinguishing between in-sample (IS) and out-of-sample (OOS) performance, and establishing minimum quality gates.

---

## Walk-Forward Validation

### Current Implementation

`strategy_research.py` implements a **70/30 temporal split**:
- **Training period (70%):** earliest bars — used for parameter optimization
- **Test period (30%):** most recent bars — used for out-of-sample validation

The split is chronological (time-based), not random. This prevents look-ahead bias where future information leaks into the training period.

### How It Works

1. Load all bars for the symbol/timeframe combination
2. Sort by datetime ascending
3. Split at the 70th percentile of bar count
4. Sweep all parameter combinations on the training data
5. Select top 5 variants by Sharpe ratio
6. Test those 5 variants on the held-out test data
7. Store IS and OOS results with `_validation` flag in params JSONB

### Current Limitations

1. **Fixed split ratio** — 70/30 is hard-coded. No sensitivity analysis for different split ratios.
2. **No multiple periods** — single train/test split. No rolling window or expanding window validation.
3. **No purging/embargo** — adjacent bars may be correlated. No gap between train and test sets. (See Lopez de Prado's Advances in Financial ML, Chapter 12.)
4. **No combinatorial purged cross-validation** — the gold standard for financial time series validation.

### Proposed Improvements

| Improvement | Priority | Effort | Notes |
|-------------|----------|--------|-------|
| Configurable split ratio | Low | 1 line | Add `--train-pct` CLI flag (already partially supported) |
| Purging/embargo between train/test | Medium | 3-5 lines | Drop N bars between train and test to reduce leakage |
| Rolling window validation | Medium | 20-30 lines | Multiple train/test windows to test consistency |
| Combinatorial purged cross-validation | High | 50-100 lines | Lopez de Prado method for financial time series |

---

## Quality Gates (Minimum Thresholds)

These gates are applied when determining whether a strategy variant is a viable candidate.

### Hard Gates (Current)

| Gate | Threshold | Source |
|------|-----------|--------|
| Minimum trade count | >= 5 | `loadStrategyResults()` Supabase query `.gte('trade_count', 5)` |
| Sharpe ratio ranking | Top 5 variants tested OOS | `strategy_research.py` |
| Data availability | At least 1 bar in result set | `resultsData.length === 0` early return |

### Soft Gates (Proposed for Future)

| Gate | Threshold | Reasoning |
|------|-----------|-----------|
| OOS Sharpe ratio | >= 1.0 | Minimum acceptable risk-adjusted return |
| Profit factor | >= 1.5 | Gross profit should significantly exceed gross loss |
| Win rate | >= 40% | Avoid strategies that win rarely but big (hard to execute psychology) |
| Max drawdown | < 50% | Catastrophic loss protection |
| IS-OOS decay | Within 30% | OOS Sharpe should not be dramatically worse than IS Sharpe |
| Calmar ratio | >= 1.0 | Return relative to worst drawdown |

---

## Metric Definitions

All metrics are computed by `strategy_research.py` and stored in `strategy_results`.

### Sharpe Ratio
- Annualized Sharpe ratio computed from daily returns
- Risk-free rate: 0% (crypto convention)
- Annualization factor: sqrt(365) for daily, sqrt(365*24) for hourly (per vibe-trading crypto engine convention)

### Total Return
- `(final_equity - initial_capital) / initial_capital * 100`
- Includes all fees and slippage

### Max Drawdown
- Maximum peak-to-trough decline in equity curve
- `max(peak - trough) / peak * 100`

### Win Rate
- `(number_of_winning_trades / total_trades) * 100`
- A trade is winning if realized P&L > 0

### Profit Factor
- `gross_profit / gross_loss`
- If gross_loss is 0, profit_factor is reported as Infinity

### Calmar Ratio
- `annualized_return / max_drawdown`
- Uses the same annualization factor as Sharpe

---

## Open Questions

1. **Should the 70/30 split be calculated by bar count or date range?** Currently by bar count. Date range would be more interpretable but may produce inconsistent sample sizes.
2. **What is the minimum number of bars required for a valid research run?** Currently implicit (must have at least enough bars for the longest indicator period). Should be explicitly documented (e.g., >= 200 bars for 4h timeframe).
3. **Should fees be configurable per run?** Currently hard-coded in `strategy_research.py`. Should be part of the strategy definition contract.
4. **How should multi-timeframe strategies be validated?** Currently each timeframe is validated independently. A strategy that uses signals from multiple timeframes would need a different validation approach.
