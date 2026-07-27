# vibe-trading Reference Summary

> **Purpose**: One-file reference for the `vibe-trading/` codebase — the READ-ONLY project we use for research patterns. This avoids re-scanning 88 skills, 462 factors, and ~2,000 files every session.

---

## 1. High-Level Overview

**What it is**: An open-source AI-powered quantitative research platform (HKUDS/vibe-trading) that combines:

- **Agent system**: LangGraph ReAct loop with 88 progressive-disclosure skills
- **Factor zoo**: 462 pre-built alphas with metadata validation (IC/IR, decay horizon, warmup bars)
- **Multi-engine backtesting**: Daily + minute engines for China A-shares, US equities, Hong Kong, **crypto (OKX)**
- **Swarm orchestration**: 29 preset multi-agent teams (investment committee, factor research, crypto desk, etc.)
- **Signal engine contract**: `generate(data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]` returning signals in [-1, 1]

**Architecture**: Single Python project with CLI, backtest engines, skill registry, data loaders (Tushare, yfinance, OKX, CCXT), and a persistent memory system. The agent loads skills on-demand and routes tasks via its system prompt.

---

## 2. Research Methodology & Prompt Patterns

### Core Workflows (from system prompt routing)

| Task Type | Pattern |
|-----------|---------|
| **Backtest** | 1. `load_skill("strategy-generate")` → 2. Write `config.json` → 3. Write `signal_engine.py` → 4. Syntax check → 5. `backtest()` → 6. Read metrics → 7. Post-backtest attribution layers |
| **Factor Research** | `load_skill("factor-research")` → compute factor CSV → compute forward returns → call `factor_analysis` tool → interpret IC/IR + quantile backtests |
| **Analysis/Research** | Load relevant skill first, then use matching tool (`factor_analysis`, `options_pricing`, `bash` for custom scripts) |

### Research Discipline (bias self-check — run at START)

| Bias | Correction |
|------|------------|
| **Leader-bias** | Deliberately search small/mid-caps and supply chain; ask "who is NOT in top-10?" |
| **English-bias** | For hardware/supply-chain, explicitly search JP/KR/TW in their languages |
| **Narrative-bias** | Ignore labels; look at actual product, unit economics, financials |
| **Confirmation-bias** | Force Munger inversion: for every bull point, search the bear case |
| **Recency-bias** | For material numbers, check date; prefer last 30 days; mark >1 year as stale |

### Goal-Driven Research (`research-goal` skill)

- Start a goal with objective + 3-5 acceptance criteria
- Add evidence linked to criteria after each data lookup / backtest / document read
- Complete only when all required criteria have verified evidence (run_id + sha256)
- Use `status="blocked"` or `"insufficient_evidence"` when evidence missing/stale/contradictory

### Strategy Generation (`strategy-generate` skill)

**The 5 design questions** (think before coding):
1. **Data** — what fields, frequency, market (determines source)
2. **Signal** — entry/exit conditions, direction, filters
3. **Position management** — equal-weight or scaling, stop-loss, max position
4. **Backtest params** — time range, initial capital (default 1M), commission (default 0.1%)
5. **Validation** — signal consistency (no NaN), position normalization, artifact completeness

**SignalEngine contract** (core abstraction):
```python
class SignalEngine:
    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        # data_map: code -> DataFrame (open, high, low, close, volume, DatetimeIndex)
        # Returns: code -> signal Series in [-1.0, 1.0]
        # 1.0 = fully long, 0.5 = half, 0.0 = flat, -1.0 = fully short
        # Portfolio: selected stocks split equally (Top N → each 1/N)
```

**Hard constraints**: signal index must align with input DataFrame; no hardcoded dates/codes; pure pandas/numpy; no external signal libs; legacy {-1, 0, 1} integers compatible.

---

## 3. Factor / Indicator Philosophy

### Categories (from `multi-factor`, `alpha-zoo`, `technical-basic`)

| Dimension | Indicators | Purpose |
|-----------|------------|---------|
| **Trend** | EMA(12/26), ADX(14) | Direction + trend strength |
| **Mean Reversion** | Bollinger Bands(20,2), RSI(14) | Overbought/oversold |
| **Volume-Price** | OBV, Volume Ratio | Confirm participation |
| **Momentum** | N-day return | Cross-sectional ranking |
| **Quality/Value** | 1/PE, 1/PB, ROE (China A-shares only) | Fundamentals |
| **Volatility** | Return std over N days | Risk filter |

### Factor Quality Criteria (from `factor-research` skill)

| Metric | Threshold | Meaning |
|--------|-----------|---------|
| **IC mean** | > 0.03 | Basic predictive power |
| **IC mean** | > 0.05 | Strong predictive power |
| **IR (IC/σ)** | > 0.5 | Stably effective |
| **IR** | > 1.0 | Extremely strong (rare) |
| **% IC > 0** | > 55% | Stable direction |

**Warning**: IC > 0.10 often indicates look-ahead bias.

### Quantile Backtest Interpretation

- **Monotonicity**: Group equity curves should rise/fall monotonically from Group 1 → N
- **Long-short spread**: Net value difference between top/bottom groups = selection power
- **Nonlinearity**: Only tails differ → factor works in extremes only
- **Stability**: Smooth curves = stable factor

### Factor Combination Methods

1. **Equal-weight**: `Z(f1) + Z(f2) + ...` (simple, good for few factors with similar IC)
2. **IC-weighted**: `w_i = |IC_i| / Σ|IC_j|`, then `Σ w_i * Z(f_i)`
3. **Orthogonalized**: Schmidt process to remove collinearity, then equal-weight

### Common Pitfalls to Avoid

- **Look-ahead bias**: Factor at T must use data ≤ T; returns must be T+1 to T+N
- **Skewed distributions**: Use cross-sectional rank/Z-score before IC
- **Industry neutralization**: Z-score within industry to remove sector effects
- **Survivorship bias**: Must include delisted instruments
- **Factor crowding**: Classic factors (momentum, value) decay over time

---

## 4. Backtesting Approach

### Crypto Engine (`backtest/engines/crypto.py`)

| Feature | Specification |
|---------|---------------|
| Trading hours | 24/7, long/short/close always allowed |
| Fees | Maker 0.02%, Taker 0.05% (opens=taker, closes=maker) |
| Slippage | 0.05% unfavorable direction |
| Funding | Every 8h (00:00/08:00/16:00 UTC), configurable rate |
| Liquidation | Maintenance margin ratio ≤ 100% → forced close |
| Position sizing | Fractional, rounded to 6 decimals |
| Annualization | 365 calendar days (not 252) |

### Config Schema (`config.json`)

```json
{
  "source": "auto|okx|tushare|yfinance|...",
  "codes": ["BTC-USDT", "ETH-USDT"],
  "start_date": "2016-03-18",
  "end_date": "2026-03-18",
  "interval": "1D|1H|1m|...",
  "initial_cash": 1000000,
  "commission": 0.001,
  "extra_fields": null,
  "optimizer": "equal_volatility|risk_parity|...|null",
  "engine": "daily|crypto|options",
  "validation": {"monte_carlo": {"n_simulations": 1000}}
}
```

### Core Metrics (always reported)

| Metric | Purpose |
|--------|---------|
| **Total Return** | Overall P&L |
| **Sharpe Ratio** | Risk-adjusted return |
| **Max Drawdown** | Worst peak-to-trough |
| **Trade Count** | Zero trades = signal bug |

### Post-Backtest Attribution Layers (auto-routed by strategy health)

| Layer | When | What |
|-------|------|------|
| **1. Trade Attribution** | Always (if trades.csv) | Top 5 winners/losers, robustness (remove top 5), exit reason breakdown, holding period buckets |
| **2. Beta Regression** | >60 trading days | OLS vs benchmark (BTC for crypto), α, β, R², t-stat |
| **3. Regime Analysis** | >1 year + Layer 2 | Bull/bear/high-vol/sideways per trade |
| **4. Monte Carlo** | validation.json exists | Permutation test p-value vs random trade order |

### Review Criteria (hard gates → `passed=false` if any fail)

1. `artifacts/metrics.csv` exists & non-empty
2. `artifacts/equity.csv` exists & non-empty
3. Exit code == 0
4. Equity column has no NaN
5. `trade_count > 0`

---

## 5. Reusable Ideas for Our Project (`crypto-etl/`)

### Immediate (Phase 3 — Indicator System)

| Idea | From vibe-trading | Adaptation |
|------|-------------------|------------|
| **Add ADX + OBV** | `technical-basic` skill | Our 6 indicators → add trend strength + volume confirmation |
| **Three-dimensional TA** | Trend + Mean-reversion + Volume voting | Structured signal combo instead of independent toggles |
| **Cross-sectional Z-score** | `multi-factor` skill | For comparing pairs on same timeframe |
| **IC/IR quality filter** | `factor-research` skill | Auto-rate indicators by backtest performance |

### Near-term (Phase 4 — Research & Strategy)

| Idea | From vibe-trading | Adaptation |
|------|-------------------|------------|
| **SignalEngine contract** | `strategy-generate` skill | `generate(ohlcv_df) -> pd.Series` in [-1, 1] for backtestability |
| **Config-driven backtest** | `config.json` schema | Simple JSON defining pair, timeframe, signal params, backtest range |
| **Post-backtest layers** | Attribution layers | At minimum: metrics + trade list + equity curve |
| **Factor decay tracking** | IC time-series | Monitor if indicator effectiveness decays |
| **Regime awareness** | `correlation-analysis` skill | Tag signals by market regime (trending/ranging) |

### Architectural Patterns to Adopt

1. **Pure pandas/numpy signals** — No external TA libraries; transparent, auditable
2. **Signal in [-1, 1]** — Continuous position sizing, not just binary
3. **Data alignment** — Signal index MUST exactly match input DataFrame index
3. **No look-ahead** — Use `.shift(1)` or `ewm` with `adjust=False` for real-time simulation
4. **Equal-weight portfolio** — Top N selected = 1/N each (simple, robust)
5. **Monte Carlo validation** — Permutation test to distinguish skill from luck

---

## 6. What to Ignore (for now)

These are advanced features in vibe-trading that are **out of scope** for our clean research terminal:

| Category | Examples | Why Skip |
|----------|----------|----------|
| **Swarm orchestration** | 29 presets, `run_swarm`, multi-agent coordination | We're single-user, single-session |
| **Persistent memory** | Cross-session `remember`/`recall`, semantic search | Local dev doesn't need it |
| **Security sandbox** | AST-level strategy code scanning | Not executing untrusted code |
| **Shadow account** | Journal parsing, behavior cloning | We don't have user trade journals |
| **Options engine** | Greeks, vol surface, complex structures | Crypto spot/perp only for now |
| **Fundamental data** | Tushare income/balance sheet, PIT-safe merge | Crypto has no fundamentals |
| **Multi-market backtest** | CompositeEngine, calendar alignment | Single-market (crypto) is fine |
| **Optimizers** | Mean-variance, risk parity, turnover-aware | Equal-weight is robust enough |
| **Document/web tools** | PDF parsing, web search/read | Not needed for price-based research |
| **Trade journal analysis** | Broker CSV parsing, behavior diagnostics | We use paper trading, not real brokers |
| **88 skills system** | Progressive disclosure, `load_skill` tool | We can hard-code our needed patterns |

---

## Quick Navigation

- **Full skill catalogue**: `vibe-trading/agent/src/skills/*/SKILL.md`
- **Crypto backtest engine**: `vibe-trading/agent/backtest/engines/crypto.py`
- **Strategy generation pattern**: `vibe-trading/agent/src/skills/strategy-generate/SKILL.md`
- **Factor research framework**: `vibe-trading/agent/src/skills/factor-research/SKILL.md`
- **Agent system prompt**: `vibe-trading/agent/src/agent/context.py` (search `_SYSTEM_PROMPT`)

---

*Generated from exploration on 2026-07-26. Update when significant patterns are added to `vibe-trading/`.*