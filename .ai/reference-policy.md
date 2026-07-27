# Reference Policy — vibe-trading/

## Status

**`vibe-trading/` is READ-ONLY.** It is an open-source AI quantitative research platform (HKUDS/vibe-trading) that we use as pattern reference only.

## Rules

1. **Never modify, format, move, rename, delete, or generate files inside `vibe-trading/`** for any reason.
2. **Never create a runtime import, package dependency, symlink, or build dependency from `crypto-etl/` to `vibe-trading/`**.
3. **Never copy files from `vibe-trading/` to `crypto-etl/`** — patterns may be independently adapted only when they solve a documented crypto-etl requirement.
4. **You may read** any file in `vibe-trading/` to understand research logic, prompts, data shapes, or architecture.

## What We Adopt From vibe-trading (Patterns Only)

| Pattern | Source | Adaptation in crypto-etl |
|---------|--------|--------------------------|
| SignalEngine contract | `strategy-generate` skill | `signal_event.md` data contract — `generate(ohlcv) -> Series[-1,1]` |
| Config-driven backtest | `config.json` schema | Strategy definition contract with params, timeframes, validation split |
| Post-backtest attribution | Attribution layers | Metrics + trade list + equity curve in strategy results |
| Pure pandas/numpy signals | Technical skills | All indicators in pure JS (no TA libs); Python research uses numpy/pandas |
| OOS/IS validation | Walk-forward | `_validation` flag in strategy results params JSONB |
| Factor decay awareness | IC/IR tracking | Documented as future goal in ROADMAP |

## What We Explicitly Do Not Adopt

| Feature | Reason |
|---------|--------|
| Swarm orchestration (29 presets) | Single-user, single-session |
| Persistent memory (Ebbinghaus decay) | Not needed for price-based research |
| Security sandbox (AST scanning) | Not executing untrusted code |
| Shadow account / journal parsing | No broker trade journals |
| Options engine (Greeks, vol surface) | Crypto spot/perp only |
| Fundamental data (Tushare, SEC) | Crypto has no fundamentals |
| Multi-market backtest (CompositeEngine) | Single-market crypto is sufficient |
| Optimizers (mean-variance, risk parity) | Equal-weight is robust enough |
| 88 skills system | Hard-code needed patterns directly |
