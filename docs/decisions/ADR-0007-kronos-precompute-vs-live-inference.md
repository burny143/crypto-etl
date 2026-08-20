# ADR-0007: Kronos Signals — Precompute via Scheduled ETL, Not Live In-Browser Inference

## Status

**Accepted** (2026)

## Context

The product needs a "Kronos + Trend" composite buy/sell overlay — a
walk-forward ensemble of a Kronos foundation-model price prediction
(formerly the `KRONOS` research project) and a transparent momentum/trend
vote. Two implementation paths were considered:

1. **Live in-browser inference**: load the Kronos model into
   `index.html` / `charts.html` via ONNX or Transformers.js and compute
   predictions on the client, mirroring how the 12+ indicators are computed
   today (`computeSMA`, `computeEMA`, `computeRSI`, ...).
2. **Precompute via scheduled Python ETL**: run `kronos_signal_etl.py`
   (PyTorch CPU) on GitHub Actions like the existing `historical_etl.py` /
   `strategy_research.py` jobs, upsert results into Supabase
   (`kronos_predictions`, `kronos_signals`), and have the browser *read* the
   results through the anon key + RLS.

## Decision

Adopt **option 2 — precomputed signals via a scheduled ETL job.** The browser
renders the precomputed `sma50` / `ensemble_vote` overlays and the
buy/sell/flat markers; it never runs Kronos inference itself.

## Why

- **Runtime reality**: Kronos is a PyTorch Transformer (the repo's model
  files total ~100MB for the 102M-param base; even `Kronos-mini` at 4.1M
  params does tokenization + autoregressive decoding). Shoehorning that into
  the browser would break the vanilla-JS, no-build architecture (ADR-0001),
  bloat the page, and make walk-forward integrity hard to audit.
- **Walk-forward honesty is simpler server-side**: the ETL stores
  `directional_accuracy_pct`, `net_return_pct`, and `buy_hold_pct` computed
  with the same no-lookahead discipline used in `direction_vote.py`; the UI
  just displays these numbers on every row instead of re-deriving them.
- **Consistent with existing data flow**: `strategy_research.py` already
  produces tables the browser reads. The schedule (daily recompute of a
  180-bar window; 4h/1h refresh of the last few bars) matches the cadence of
  the existing workflows and keeps the model evaluation reproducible.
- **The 30 symbols × 3 timeframes matrix is too large for the client** to
  re-run per symbol switch without repeated model loads, whereas the ETL
  amortizes one model load across all series.

## Consequences

**Positive:**
- No browser-side model runtime; page stays light and no-build.
- Signals are persisted and auditable; honest metrics travel with the data.
- Same upsert/RLS pattern as `strategy_results` (V5), `paper_signals` (V8).

**Negative:**
- Signals are only as fresh as the last scheduled run (daily for full
  coverage; intraday refreshes only touch the trailing bars).
- More moving parts (new workflow, new tables, model weights must be
  downloadable on the runner).

**Mitigations:**
- `Kronos-mini` (4.1M params, ctx 2048) is the default model to keep
  per-run CPU time sane; configurable via `KRONOS_MODEL_ID` / `--model`.
- The daily job recomputes the full 180-bar window; 1h/4h jobs use
  `--recent-bars` to refresh only the newest bars.
- Honesty contract enforced in the ETL (see
  `docs/data-contracts/kronos-signal.md`) and in ADR-0005: the overlay is a
  research artifact with visible metrics, not a guaranteed edge.

## Future Consideration

If live client-side inference ever becomes viable (e.g. a distilled
quantized model small enough to export), it could be layered on top of the
precomputed pipeline as a "live refresh" of the trailing bar only — the
schema and rendering path would not change.