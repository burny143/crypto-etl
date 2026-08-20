#!/usr/bin/env python3
"""
kronos_signal_etl.py — Kronos + Trend composite signal ETL

Computes a walk-forward, no-lookahead composite buy/sell signal per
(symbol, timeframe) from data already stored in Supabase ``crypto_historical``,
then upserts the results into two new tables:

  * ``kronos_predictions`` — one row per (symbol, timeframe, bar_timestamp):
    predicted_close (Kronos 1-bar-ahead walk-forward), sma50, ensemble_vote,
    model_used.
  * ``kronos_signals``    — one row per (symbol, timeframe, bar_timestamp):
    signal ('buy'/'sell'/'flat'), reason, plus walk-forward honesty metrics
    for that symbol/timeframe (net_return_pct vs buy_and_hold_pct,
    directional_accuracy_pct, evaluated_from, evaluated_to).

Signal rule (kept deliberately simple and isolated in
``derive_composite_signals`` so it is easy to inspect/replace later):

  LONG  when  close > SMA(50)  AND  ensemble_vote > 0
  FLAT  otherwise (exit when either condition fails)

where the ensemble vote is the direction_vote.py logic ported from the KRONOS
workspace: sign(kronos_sign + linear_sign), with the linear model refit
walk-forward on trailing momentum features (mom2/5/10/20/60, vol20, lag
prediction error, log price) using a FIT_WIN=90 rolling window.

Honesty contract (from the KRONOS project findings — do not "fix"):
  * Raw Kronos direction has NO validated edge (sign accuracy ~40-49% on
    BTC/ETH at daily/4h). The composite signal is presented as a research
    overlay, not a guaranteed edge.
  * Directional accuracy is ALWAYS predicted-vs-last-actual-close; never
    pct_change() of the prediction series.
  * Metrics are stored alongside the signals so the UI can show whether this
    symbol/timeframe has historically had an edge — including when it has not.

Environment: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

Usage:
    python kronos_signal_etl.py --timeframes 1d                 # daily job
    python kronos_signal_etl.py --timeframes 4h --recent-bars 6 # 4h refresh
    python kronos_signal_etl.py --timeframes 1h --recent-bars 2 # hourly refresh
    python kronos_signal_etl.py --symbols BTC-USDT --timeframes 1d --no-upload
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ALL_SYMBOLS = [
    "BTC-USDT", "ETH-USDT", "XRP-USDT", "SOL-USDT", "BNB-USDT",
    "ADA-USDT", "DOGE-USDT", "AVAX-USDT", "DOT-USDT", "LINK-USDT",
    "UNI-USDT", "SHIB-USDT", "LTC-USDT", "BCH-USDT", "ATOM-USDT",
    "ETC-USDT", "XLM-USDT", "FIL-USDT", "TRX-USDT", "NEAR-USDT",
    "APT-USDT", "ARB-USDT", "OP-USDT", "SUI-USDT", "PEPE-USDT",
    "INJ-USDT", "TIA-USDT", "POL-USDT", "SEI-USDT", "STRK-USDT",
]
DEFAULT_TIMEFRAMES = ["1d", "4h", "1h"]

# Default model: Kronos-mini (4.1M params, ctx 2048, tokenizer-2k) — small
# enough to run across many symbol/timeframe combos on a CPU-only GitHub
# Actions runner. Override with KRONOS_MODEL_ID / KRONOS_TOKENIZER_ID env vars.
DEFAULT_MODEL_ID = os.environ.get("KRONOS_MODEL_ID", "NeoQuasar/Kronos-mini")
DEFAULT_TOKENIZER_ID = os.environ.get("KRONOS_TOKENIZER_ID", "NeoQuasar/Kronos-Tokenizer-2k")
DEFAULT_MAX_CONTEXT = int(os.environ.get("KRONOS_MAX_CONTEXT", "2048"))

LOOKBACK = 400            # history window fed to Kronos (safe on ctx-512/2048)
FIT_WIN = 90              # rolling window for the walk-forward linear vote
LAMBDA = 1e-3             # ridge regularization for the linear vote
FEE = 0.001               # per-side fee for the long/flat net-return metric
SMA_PERIOD = 50           # trend filter period
BATCH_SIZE = 500


# ---------------------------------------------------------------------------
# Pure signal logic (no torch, no Supabase — unit-testable without a model)
# ---------------------------------------------------------------------------

def sma50(closes: np.ndarray) -> np.ndarray:
    """50-bar simple moving average with NaN in the warm-up window."""
    arr = np.asarray(closes, dtype=float)
    out = np.full(len(arr), np.nan)
    if len(arr) < SMA_PERIOD:
        return out
    csum = np.cumsum(np.insert(arr, 0, 0.0))
    for i in range(SMA_PERIOD - 1, len(arr)):
        out[i] = (csum[i + 1] - csum[i + 1 - SMA_PERIOD]) / SMA_PERIOD
    return out


def ridge_beta(X: np.ndarray, y: np.ndarray, lam: float) -> np.ndarray:
    """Closed-form ridge regression beta: (X'X + lam*I)^-1 X'y."""
    return np.linalg.solve(X.T @ X + lam * np.eye(X.shape[1]), X.T @ y)


def build_vote_features(
    closes: np.ndarray, predicted_close: np.ndarray, actual_close: np.ndarray
) -> pd.DataFrame:
    """
    Momentum/vol/error features for the walk-forward ensemble vote.

    Ported from the KRONOS workspace direction_vote.py. Features for bar i use
    only information available at the close of bar i-1 (no lookahead):
      mom2/5/10/20/60  — trailing momentum over k bars, in %
      vol20            — 20-bar std of daily returns, in %
      lag_err          — previous bar's Kronos prediction error
      log_price        — log of the previous close
    Index: same as the input arrays (bar positions).
    """
    closes = np.asarray(closes, dtype=float)
    pred = np.asarray(predicted_close, dtype=float)
    actual = np.asarray(actual_close, dtype=float)
    n = len(closes)
    feats = np.full((n, 8), np.nan)

    for j, k in enumerate((2, 5, 10, 20, 60)):
        prev = np.full(n, np.nan)
        past = np.full(n, np.nan)
        prev[1:] = closes[:-1]
        if k + 1 < n:
            past[k + 1:] = closes[: n - k - 1]
        with np.errstate(invalid="ignore", divide="ignore"):
            feats[:, j] = (prev / past - 1.0) * 100.0

    rets = np.full(n, np.nan)
    rets[1:] = closes[1:] / closes[:-1] - 1.0
    roll = np.full(n, np.nan)
    for i in range(20, n):
        roll[i] = np.nanstd(rets[i - 19 : i + 1])
    feats[:, 5] = roll * 100.0

    raw_err = actual - pred
    lag = np.full(n, np.nan)
    lag[1:] = raw_err[:-1]
    feats[:, 6] = lag

    with np.errstate(invalid="ignore", divide="ignore"):
        feats[:, 7] = np.log(np.where(np.isnan(prev), np.nan, prev))

    df = pd.DataFrame(feats, columns=["mom2", "mom5", "mom10", "mom20", "mom60", "vol20", "lag_err", "log_price"])
    return df


def walk_forward_vote(feats: pd.DataFrame, actual_sign: np.ndarray, fit_win: int = FIT_WIN, lam: float = LAMBDA) -> np.ndarray:
    """
    Walk-forward linear-model vote on the sign of next-bar direction.

    For bar i (i >= fit_win): refit ridge on bars [i-fit_win, i) and predict
    bar i's feature vector, producing sign(+1/-1) or NaN during warm-up.
    Pure numpy loop — matches direction_vote.py semantics (no lookahead).
    """
    X_all = feats.values.astype(float)
    n = X_all.shape[0]
    l_sig = np.full(n, np.nan)
    for i in range(fit_win, n):
        X = X_all[i - fit_win : i]
        y = actual_sign[i - fit_win : i]
        mask = ~(np.isnan(X).any(axis=1) | np.isnan(y))
        if mask.sum() < max(5, X.shape[1] + 1):
            continue
        beta = ridge_beta(X[mask], y[mask], lam)
        v = X_all[i]
        if np.isnan(v).any():
            continue
        l_sig[i] = float(np.sign(v @ beta)) if np.sign(v @ beta) != 0 else 1.0
    return l_sig


def derive_composite_signals(
    closes: np.ndarray,
    sma: np.ndarray,
    vote: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Composite signal rule (isolated for easy inspection/change):

      LONG when (close > SMA(50)) AND (ensemble vote > 0)
      FLAT otherwise — exit when either condition fails

    Returns (signals, position):
      signals   — per-bar 'buy'/'sell'/'flat' (transition-triggered)
      position  — per-bar 1 (long) / 0 (flat), decided at prior close

    Walk-forward convention (matches direction_vote.py): the signal for bar i
    is decided from data available at the close of bar i-1 (close_{i-1},
    SMA_{i-1}, vote_i which itself uses info up to i-1), then held for bar i's
    return. Not everything a UI user sees is a live-trade promise — this is
    the research rule, applied consistently with the KRONOS findings.
    """
    closes = np.asarray(closes, dtype=float)
    sma = np.asarray(sma, dtype=float)
    vote = np.asarray(vote, dtype=float)
    n = len(closes)

    # Condition evaluated on the previous close (decided at close of bar i-1)
    prev_close = np.full(n, np.nan)
    prev_close[1:] = closes[:-1]
    prev_sma = np.full(n, np.nan)
    prev_sma[1:] = sma[:-1]

    # Long condition for bar i uses close_{i-1} vs sma_{i-1} AND vote_i (<=0 flat)
    with np.errstate(invalid="ignore"):
        long_cond = (prev_close > prev_sma) & (vote > 0)
    long_cond = np.where(np.isnan(prev_close) | np.isnan(prev_sma) | np.isnan(vote), False, long_cond)

    position = long_cond.astype(int)
    prev_pos = np.zeros(n, dtype=int)
    prev_pos[1:] = position[:-1]

    signals = np.full(n, "flat", dtype=object)
    # Entry: position flips 0 -> 1 (marker on the bar being traded)
    signals[(position == 1) & (prev_pos == 0)] = "buy"
    # Exit:  position flips 1 -> 0
    signals[(position == 0) & (prev_pos == 1)] = "sell"
    return signals, position


def walk_forward_metrics(
    closes: np.ndarray,
    position: np.ndarray,
    vote: np.ndarray,
    timestamps: pd.DatetimeIndex | np.ndarray,
    fee: float = FEE,
) -> dict:
    """
    Honest walk-forward sanity metrics over the evaluated range.

      net_return_pct            — long/flat equity compounding with `fee` per
                                  entry, exited at the end of the range
      buy_hold_pct              — buy-and-hold over the same bars
      directional_accuracy_pct  — sign(vote) == sign(actual move), compared
                                  against the LAST ACTUAL CLOSE (never
                                  pct_change of the prediction series)
      evaluated_from / _to      — first/last evaluated bar timestamp

    NaN warm-up bars and leading non-finite values are trimmed so the metrics
    only cover bars where the vote was actually computable.
    """
    closes = np.asarray(closes, dtype=float)
    position = np.asarray(position, dtype=float)
    vote = np.asarray(vote, dtype=float)
    n = len(closes)
    if n < 2:
        return {}

    # Actual one-bar returns
    actual_ret = np.full(n, np.nan)
    actual_ret[1:] = closes[1:] / closes[:-1] - 1.0
    actual_sign = np.full(n, np.nan)
    actual_sign[1:] = np.sign(actual_ret[1:])

    valid = ~(np.isnan(vote) | np.isnan(actual_ret) | np.isnan(position))
    valid[0] = False  # no return to earn on the first bar
    idx = np.where(valid)[0]
    if len(idx) == 0:
        return {}

    start_i, end_i = int(idx[0]), int(idx[-1])

    # Directional accuracy of the vote (predicted-vs-last-close, never pct_change of preds)
    dir_mask = ~(np.isnan(vote[start_i : end_i + 1]) | np.isnan(actual_sign[start_i : end_i + 1]))
    if dir_mask.sum() > 0:
        matches = np.sign(vote[start_i : end_i + 1][dir_mask]) == actual_sign[start_i : end_i + 1][dir_mask]
        dir_acc = float(matches.mean()) * 100.0
    else:
        dir_acc = float("nan")

    # Long/flat net return with per-entry fee (position decided at prior close)
    pos = position[start_i : end_i + 1]
    rets = actual_ret[start_i : end_i + 1]
    gross = pos * np.nan_to_num(rets, nan=0.0)
    entries = np.zeros_like(pos)
    entries[0] = 1 if pos[0] == 1 else 0  # enter if long at start
    entries[1:] = np.maximum(pos[1:] - pos[:-1], 0)
    net = gross - fee * entries
    net_return_pct = (float(np.prod(1.0 + net)) - 1.0) * 100.0
    buy_hold_pct = (float(np.prod(1.0 + np.nan_to_num(rets, nan=0.0))) - 1.0) * 100.0

    ts = list(timestamps)
    return {
        "net_return_pct": net_return_pct,
        "buy_hold_pct": buy_hold_pct,
        "directional_accuracy_pct": dir_acc,
        "evaluated_from": ts[start_i],
        "evaluated_to": ts[end_i],
        "evaluated_bars": int(len(idx)),
    }


# ---------------------------------------------------------------------------
# Supabase helpers (lazy import — unit tests don't need the SDK installed)
# ---------------------------------------------------------------------------

def _supabase():
    from supabase import create_client

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
    return create_client(url, key)


def load_ohlcv(supabase, symbol: str, timeframe: str) -> pd.DataFrame | None:
    """Fetch OHLCV bars for one symbol/timeframe from Supabase, sorted ascending."""
    try:
        resp = (
            supabase.table("crypto_historical")
            .select("datetime,open,high,low,close,volume")
            .eq("symbol", symbol)
            .eq("timeframe", timeframe)
            .order("datetime", desc=False)
            .execute()
        )
    except Exception as e:
        print(f"  [ERR] Supabase query failed for {symbol} [{timeframe}]: {e}")
        return None
    if not resp.data or len(resp.data) < LOOKBACK + FIT_WIN:
        return None
    df = pd.DataFrame(resp.data)
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    df = df.set_index("datetime")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df.dropna(subset=["open", "high", "low", "close", "volume"], inplace=True)
    return df.sort_index()


def upsert_batch(supabase, table: str, rows: list[dict], on_conflict: str):
    """Upsert rows into a Supabase table in BATCH_SIZE chunks, logging errors."""
    if not rows:
        return
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        try:
            supabase.table(table).upsert(batch, on_conflict=on_conflict).execute()
            print(f"    Upserted {table} rows {i + 1}-{i + len(batch)} of {len(rows)}")
        except Exception as e:
            print(f"    ERROR upserting {table} batch {i + 1}-{i + len(batch)}: {e}")


# ---------------------------------------------------------------------------
# Kronos inference (lazy import — the model only loads when actually running)
# ---------------------------------------------------------------------------

def load_predictor(model_id: str, tokenizer_id: str, max_context: int):
    """Load the vendored Kronos model + tokenizer from HuggingFace Hub."""
    import torch  # noqa: F401  (import asserted so torch errors surface clearly)

    from kronos_model.model import Kronos, KronosTokenizer, KronosPredictor

    tokenizer = KronosTokenizer.from_pretrained(tokenizer_id)
    model = Kronos.from_pretrained(model_id)
    predictor = KronosPredictor(model, tokenizer, device="cpu", max_context=max_context)
    print(f"  Loaded model {model_id} + tokenizer {tokenizer_id} (ctx={max_context})")
    return predictor


def predict_bars_walkforward(
    predictor,
    df: pd.DataFrame,
    lookback: int,
    eval_start: int,
    eval_end: int,
    sample_count: int = 1,
) -> pd.DataFrame:
    """
    Walk-forward 1-bar-ahead Kronos predictions for bar positions
    [eval_start, eval_end) in `df`. Prediction for bar i uses ONLY the
    `lookback` bars ending at i-1 (no lookahead). Returns a Series indexed by
    bar timestamp with the predicted close.

    One model call per evaluated bar (sample_count=1 default keeps CPU time
    sane on a free GitHub Actions runner).
    """
    freq = df.index[1] - df.index[0]
    n = len(df)
    rows = []
    for i in range(eval_start, eval_end):
        if i < lookback:
            continue
        x = df.iloc[i - lookback : i]
        # KronosPredictor.predict's calc_time_stamps() requires pandas.Series
        # (it uses the .dt accessor); a DatetimeIndex has no .dt and raises
        # AttributeError. This was the original "ETL ran but wrote 0 rows" bug.
        x_timestamp = pd.Series(x.index.values, index=x.index)
        y_timestamp = pd.Series([df.index[i].to_pydatetime()])
        try:
            pred = predictor.predict(
                df=x.drop(columns=[]),  # predictor accepts columns open/high/low/close/volume/amount
                x_timestamp=x_timestamp,
                y_timestamp=y_timestamp,
                pred_len=1,
                T=1.0,
                top_p=0.9,
                sample_count=sample_count,
                verbose=False,
            )
            rows.append((df.index[i], float(pred["close"].iloc[0])))
        except Exception as e:
            print(f"    [WARN] prediction failed at {df.index[i]}: {e}")
    if not rows:
        return pd.DataFrame(columns=["timestamp", "predicted_close"])
    out = pd.DataFrame(rows, columns=["timestamp", "predicted_close"]).set_index("timestamp")
    return out


# ---------------------------------------------------------------------------
# Per-series pipeline
# ---------------------------------------------------------------------------

def process_series(
    supabase,
    symbol: str,
    timeframe: str,
    max_eval_bars: int,
    recent_bars: int,
    predictor=None,
    model_id: str = DEFAULT_MODEL_ID,
    no_upload: bool = False,
) -> dict:
    """Compute and (optionally) upsert predictions + signals for one series."""
    df = load_ohlcv(supabase, symbol, timeframe)
    if df is None:
        return {"symbol": symbol, "timeframe": timeframe, "status": "no-data", "bars": 0}

    closes = df["close"].to_numpy(dtype=float)
    n = len(closes)

    # Which bars do we (re)compute? Default: the trailing max_eval_bars.
    # recent_bars > 0 means "only recompute the last N bars" (cheap refresh
    # for intraday cadences; historical rows from the daily job stay).
    if recent_bars and recent_bars > 0:
        eval_start = max(0, n - recent_bars)
        eval_end = n
    else:
        eval_end = n
        eval_start = max(0, n - max_eval_bars)
    # We need LOOKBACK bars before the first evaluated bar; scoot forward if not.
    eval_start = max(eval_start, lookback_needed())
    if eval_end <= eval_start:
        return {"symbol": symbol, "timeframe": timeframe, "status": "too-small", "bars": n}

    print(f"  {symbol} [{timeframe}] bars={n} eval=[{eval_start},{eval_end})")
    if predictor is not None:
        t0 = time.time()
        pred_df = predict_bars_walkforward(predictor, df, LOOKBACK, eval_start, eval_end)
        print(f"    Walk-forward predictions: {len(pred_df)} bars in {time.time() - t0:.1f}s")
        if pred_df.empty:
            return {"symbol": symbol, "timeframe": timeframe, "status": "no-preds", "bars": n}
        pred_series = pred_df["predicted_close"]
    else:
        # Predictor is None — dry logic mode for tests/CI without a model.
        # Use the previous close as a "dummy" predicted close so the signal
        # pipeline can still be validated end-to-end.
        dummy = np.full(n, np.nan)
        dummy[1:] = closes[:-1]
        pred_series = pd.Series(dummy, index=df.index)

    # Align prediction rows to the full bar index (reindexing is required:
    # the walk-forward predictor returns rows only for the evaluated window,
    # which is usually shorter than the full series).
    pred_series = pred_series.reindex(df.index)
    pred_values = pred_series.to_numpy(dtype=float)
    actual = closes[:]

    # SMA(50) on full closes (index stays aligned)
    sma = sma50(closes)

    # Ensemble vote (direction_vote.py port)
    feats = build_vote_features(closes, np.nan_to_num(pred_values), actual)
    actual_sign = np.sign(np.append([np.nan], np.diff(closes)))
    lin_vote = walk_forward_vote(feats, actual_sign, fit_win=FIT_WIN, lam=LAMBDA)

    # Vote per evaluated bar: kronos sign(pred_i - close_{i-1}) + linear sign
    close_prev = np.full(n, np.nan)
    close_prev[1:] = closes[:-1]
    k_sig = np.sign(np.nan_to_num(pred_values) - np.nan_to_num(close_prev))
    vote = np.sign(k_sig + lin_vote)  # sign(0) = 0 (tie) — matches direction_vote.py

    # Composite signal rule
    signals, position = derive_composite_signals(closes, sma, vote)

    # Metrics over the recently-evaluated (non-NaN) range
    ts = df.index
    metrics = walk_forward_metrics(closes, position, vote, ts, fee=FEE)

    if not metrics:
        return {"symbol": symbol, "timeframe": timeframe, "status": "no-metrics", "bars": n}

    # Build rows
    pred_rows, sig_rows = [], []
    for i in range(eval_start, eval_end):
        t = df.index[i]
        pc = pred_series.get(t) if hasattr(pred_series, "get") else None
        if pc is None or (isinstance(pc, float) and math.isnan(pc)):
            continue
        pred_rows.append({
            "symbol": symbol,
            "timeframe": timeframe,
            "bar_timestamp": t.isoformat(),
            "predicted_close": _sf(pc),
            "sma50": _sf(sma[i]),
            "ensemble_vote": _sf(vote[i]),
            "model_used": model_id,
        })
        sig_rows.append({
            "symbol": symbol,
            "timeframe": timeframe,
            "bar_timestamp": t.isoformat(),
            "signal": str(signals[i]),
            "reason": _signal_reason(signals[i], closes, sma, vote, i),
            "model_used": model_id,
            "net_return_pct": _sf(metrics["net_return_pct"]),
            "buy_hold_pct": _sf(metrics["buy_hold_pct"]),
            "directional_accuracy_pct": _sf(metrics["directional_accuracy_pct"]),
            "evaluated_from": metrics["evaluated_from"].isoformat(),
            "evaluated_to": metrics["evaluated_to"].isoformat(),
            "evaluated_bars": int(metrics["evaluated_bars"]),
        })

    if no_upload:
        print(f"    [dry-run] {len(pred_rows)} prediction rows, {len(sig_rows)} signal rows")
        return {"symbol": symbol, "timeframe": timeframe, "status": "dry-run", "bars": n,
                "pred_rows": len(pred_rows), "sig_rows": len(sig_rows), "metrics": metrics}

    upsert_batch(supabase, "kronos_predictions", pred_rows, on_conflict="symbol,timeframe,bar_timestamp")
    upsert_batch(supabase, "kronos_signals", sig_rows, on_conflict="symbol,timeframe,bar_timestamp")

    m = metrics
    print(f"    net_return={m['net_return_pct']:+.2f}% vs buy_hold={m['buy_hold_pct']:+.2f}% "
          f"dir_acc={m['directional_accuracy_pct']:.1f}% ({m['evaluated_bars']} bars, "
          f"{m['evaluated_from'].date()} -> {m['evaluated_to'].date()})")
    return {"symbol": symbol, "timeframe": timeframe, "status": "ok", "bars": n,
            "pred_rows": len(pred_rows), "sig_rows": len(sig_rows), "metrics": m}


def lookback_needed() -> int:
    return LOOKBACK


def _signal_reason(sig: str, closes: np.ndarray, sma: np.ndarray, vote: np.ndarray, i: int) -> str:
    if sig == "buy":
        return "close_above_sma50_and_vote_gt_0"
    if sig == "sell":
        if i > 0 and closes[i - 1] <= (sma[i - 1] if not math.isnan(sma[i - 1]) else -np.inf):
            return "close_below_or_equal_sma50"
        return "vote_le_0"
    return "flat"


def _sf(val):
    """Safe float (NaN/inf -> None)."""
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global LOOKBACK

    parser = argparse.ArgumentParser(description="Kronos + Trend composite signal ETL")
    parser.add_argument("--symbols", default=",".join(ALL_SYMBOLS), help="Comma-separated symbols (default: all 30)")
    parser.add_argument("--timeframes", default=",".join(DEFAULT_TIMEFRAMES), help="Comma-separated timeframes")
    parser.add_argument("--max-eval-bars", type=int, default=180, help="Trailing bars fully recomputed (daily job)")
    parser.add_argument("--recent-bars", type=int, default=0, help=">0 = only recompute last N bars (cheap intraday refresh)")
    parser.add_argument("--lookback", type=int, default=LOOKBACK, help="History window for Kronos")
    parser.add_argument("--model", default=DEFAULT_MODEL_ID, help="Kronos model id (default: Kronos-mini)")
    parser.add_argument("--tokenizer", default=DEFAULT_TOKENIZER_ID, help="Kronos tokenizer id")
    parser.add_argument("--max-context", type=int, default=DEFAULT_MAX_CONTEXT, help="Kronos max_context")
    parser.add_argument("--sample-count", type=int, default=1, help="Kronos sample_count (1 = fastest)")
    parser.add_argument("--no-upload", action="store_true", help="Dry run: compute + print, do not upsert")
    args = parser.parse_args()
    LOOKBACK = args.lookback

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    timeframes = [t.strip() for t in args.timeframes.split(",") if t.strip()]

    print("=" * 70)
    print("KRONOS + TREND SIGNAL ETL")
    print(f"UTC: {datetime.now(timezone.utc).isoformat()}")
    print(f"Symbols: {len(symbols)} | Timeframes: {timeframes}")
    print(f"Model: {args.model} | tokenizer: {args.tokenizer} | ctx: {args.max_context}")
    print(f"max_eval_bars={args.max_eval_bars} recent_bars={args.recent_bars} lookback={LOOKBACK}")
    print("=" * 70)

    supabase = _supabase()

    predictor = None
    if not args.no_upload or args.symbols != "NONE":
        # Even in dry-run we want real Kronos predictions; load the model
        # unless the caller explicitly passed --symbols NONE (logic-only).
        if args.symbols != "NONE":
            t0 = time.time()
            predictor = load_predictor(args.model, args.tokenizer, args.max_context)
            print(f"  Model load time: {time.time() - t0:.1f}s")

    t_start = time.time()
    results = []
    for timeframe in timeframes:
        print(f"\n--- Timeframe: {timeframe} ---")
        for symbol in symbols:
            try:
                r = process_series(
                    supabase, symbol, timeframe,
                    max_eval_bars=args.max_eval_bars,
                    recent_bars=args.recent_bars,
                    predictor=predictor,
                    model_id=args.model,
                    no_upload=args.no_upload,
                )
                results.append(r)
            except Exception as exc:
                print(f"  ERROR {symbol} [{timeframe}]: {exc}")
                results.append({"symbol": symbol, "timeframe": timeframe, "status": "error", "error": str(exc)})

    ok = [r for r in results if r.get("status") == "ok"]
    dry = [r for r in results if r.get("status") == "dry-run"]
    missing = [r for r in results if r.get("status") in ("no-data", "too-small", "no-preds", "no-metrics")]
    errors = [r for r in results if r.get("status") == "error"]

    print(f"\n{'=' * 70}")
    print(f"Done in {time.time() - t_start:.1f}s")
    print(f"  OK: {len(ok)} series | dry-run: {len(dry)} | missing/skipped: {len(missing)} | errors: {len(errors)}")
    if missing:
        print("  Skipped (no data / too small / no computable metrics):")
        for r in missing:
            print(f"    {r['symbol']} [{r['timeframe']}] ({r['status']}, bars={r.get('bars')})")
    if errors:
        print("  Errors:")
        for r in errors:
            print(f"    {r['symbol']} [{r['timeframe']}]: {r.get('error')}")
    print("=" * 70)

    # Honest CPU-budget note (see ADR-0007): full 30x3 coverage is recomputed
    # in the daily job; intraday jobs refresh only the last few bars. If a
    # runner's time budget is still the bottleneck, narrow --symbols to a
    # curated subset — never silently truncate coverage.
    if ok or dry:
        print("\nNote: intraday cadences only refresh the last few bars per run.")
        print("Expand coverage by raising --recent-bars / --max-eval-bars or run the daily job.")


if __name__ == "__main__":
    main()