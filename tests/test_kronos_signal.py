#!/usr/bin/env python3
"""Unit tests for the Kronos + Trend composite signal logic.

These tests exercise the pure, testable pieces of kronos_signal_etl.py
(sma50, ridge_beta, build_vote_features, walk_forward_vote,
derive_composite_signals, walk_forward_metrics, process_series in
no-upload mode) without loading a torch model or contacting Supabase.
"""

import math

import numpy as np
import pandas as pd

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kronos_signal_etl as kse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def monotonic_closes(n: int = 500, start: float = 100.0, step: float = 0.3) -> np.ndarray:
    """A clean uptrend with small noise — a trend filter should love it."""
    rng = np.random.default_rng(7)
    returns = np.full(n, 1.0 + step / start) + rng.normal(0, 0.0004, n)
    closes = np.cumprod(np.concatenate([[start], returns[1:]]))
    return closes


def synth_df(closes: np.ndarray, freq: str = "1D") -> pd.DataFrame:
    """OHLCV DataFrame indexed by DatetimeIndex, matching crypto_historical."""
    idx = pd.date_range("2024-01-01", periods=len(closes), freq=freq, tz="UTC")
    return pd.DataFrame(
        {
            "open": closes * 0.999,
            "high": closes * 1.005,
            "low": closes * 0.995,
            "close": closes,
            "volume": np.linspace(100, 200, len(closes)),
        },
        index=idx,
    )


# ---------------------------------------------------------------------------
# sma50
# ---------------------------------------------------------------------------

def test_sma50_warmup_has_nan_then_tracks_value():
    closes = np.arange(1.0, 101.0)
    sma = kse.sma50(closes)
    assert len(sma) == len(closes)
    assert np.isnan(sma[:49]).all(), "warm-up window should be NaN"
    assert not np.isnan(sma[49:]).any(), "SMA should be defined from bar 49 on"
    # Last SMA(50) of 1..100 = mean(51..100) = 75.5
    assert abs(sma[-1] - 75.5) < 1e-9


def test_sma50_short_series_all_nan():
    sma = kse.sma50(np.arange(10.0))
    assert np.isnan(sma).all()


# ---------------------------------------------------------------------------
# ridge_beta
# ---------------------------------------------------------------------------

def test_ridge_beta_solves_simple_case():
    # Perfect linear relationship y = 2x + 1, tiny lambda -> close to OLS
    X = np.array([[1.0, 1.0], [2.0, 1.0], [3.0, 1.0], [4.0, 1.0]])
    y = np.array([3.0, 5.0, 7.0, 9.0])
    beta = kse.ridge_beta(X, y, lam=1e-9)
    assert abs(beta[0] - 2.0) < 1e-3
    assert abs(beta[1] - 1.0) < 1e-3


def test_ridge_beta_regularizes():
    X = np.array([[1.0, 1.0], [2.0, 1.0], [3.0, 1.0], [4.0, 1.0]])
    y = np.array([3.0, 5.0, 7.0, 9.0])
    beta_hi = kse.ridge_beta(X, y, lam=10.0)
    beta_lo = kse.ridge_beta(X, y, lam=1e-9)
    # Stronger ridge should pull the slope toward zero
    assert abs(beta_hi[0]) < abs(beta_lo[0])


# ---------------------------------------------------------------------------
# build_vote_features
# ---------------------------------------------------------------------------

def test_build_vote_features_no_lookahead_and_momentum():
    closes = monotonic_closes(200)
    pred = closes.copy()
    actual = closes.copy()
    feats = kse.build_vote_features(closes, pred, actual)

    assert list(feats.columns) == ["mom2", "mom5", "mom10", "mom20", "mom60", "vol20", "lag_err", "log_price"]

    # mom2[i] = (close[i-1] / close[i-3] - 1) * 100  (uses only info at i-1)
    i = 100
    expected = (closes[i - 1] / closes[i - 3] - 1.0) * 100.0
    assert abs(feats["mom2"].iloc[i] - expected) < 1e-9

    # Flipped check: mom2 must NOT use close[i]
    assert math.isnan(feats["mom2"].iloc[1]), "warm-up should be NaN"
    assert not math.isnan(feats["mom2"].iloc[10])

    # lag_err[i] = actual[i-1] - pred[i-1]
    assert abs(feats["lag_err"].iloc[i] - (actual[i - 1] - pred[i - 1])) < 1e-9

    # log_price[i] = log(close[i-1])
    assert abs(feats["log_price"].iloc[i] - math.log(closes[i - 1])) < 1e-9


def test_build_vote_features_full_length_input_only():
    # build_vote_features expects arrays already aligned to the full series;
    # short prediction windows must be reindexed upstream in process_series.
    closes = monotonic_closes(300)
    pred = np.full(300, np.nan)
    pred[150:] = closes[150:]  # simulate "only the eval window has predictions"
    actual = closes.copy()
    feats = kse.build_vote_features(closes, pred, actual)
    assert len(feats) == len(closes), "features must align to the full series"
    # lag_err is NaN where prediction is missing
    assert np.isnan(feats["lag_err"].iloc[100])
    assert not np.isnan(feats["lag_err"].iloc[200])


# ---------------------------------------------------------------------------
# walk_forward_vote
# ---------------------------------------------------------------------------

def test_walk_forward_vote_warmup_and_sign():
    rng = np.random.default_rng(3)
    n = 220
    # Construct a feature that perfectly predicts the next-bar sign so the
    # linear model should recover a correct vote in the walk-forward part.
    closes = np.linspace(100, 110, n)
    direction = np.sign(np.append([np.nan], np.diff(closes)))
    feats = pd.DataFrame({"mom2": 1.0, "vol20": 0.5, "lag_err": 0.0, "log_price": np.log(closes)})
    feats["mom2"] = direction  # feature = previous direction signal

    vote = kse.walk_forward_vote(feats, direction, fit_win=30, lam=1e-3)
    assert np.isnan(vote[:30]).all(), "warm-up should be NaN"
    assert not np.isnan(vote[30:]).any()
    nonzero = vote[30:]
    assert (nonzero != 0).all(), "a perfect feature should yield a signed vote"
    assert (nonzero > 0).all(), "synthetic up-trend should vote long"


# ---------------------------------------------------------------------------
# derive_composite_signals
# ---------------------------------------------------------------------------

def test_derive_composite_signals_rule():
    n = 120
    closes = monotonic_closes(n, start=100.0, step=0.3)
    sma = kse.sma50(closes)
    # Vote negative for bars [0,60), positive for [60,90), negative after
    vote = np.full(n, -1.0)
    vote[60:90] = 1.0

    signals, position = kse.derive_composite_signals(closes, sma, vote)

    assert len(signals) == n and len(position) == n

    buys = np.where(signals == "buy")[0]
    sells = np.where(signals == "sell")[0]

    # First entry at bar 60: vote turns positive AND prev_close > prev_sma
    # (SMA defined from bar 49, and prev_close=close[59] sits well above it)
    assert len(buys) >= 1
    assert buys[0] == 60, f"first entry should be at bar 60, got {buys[0]}"
    # Exit when vote flips negative at bar 90
    assert len(sells) >= 1
    assert sells[0] == 90, f"exit should be at bar 90, got {sells[0]}"
    # Position bookkeeping: long exactly when both conditions hold
    assert position[60] == 1 and position[90] == 0


def test_derive_composite_signals_no_lookahead():
    # Signal at bar i must be decided from close/SMA at i-1 (prev_close/prev_sma)
    closes = np.arange(100.0, 160.0)
    sma = np.full(60, 100.0)  # constant SMA => close > sma always in warm valid range
    vote = np.full(60, 1.0)
    signals, _ = kse.derive_composite_signals(closes, sma, vote)
    # Bar 1 uses prev_close=close[0]=100 and prev_sma=sma[0]=100 -> NOT > => flat
    assert "buy" not in signals[:2], "no entry without a strictly greater prev close"
    assert signals[1] == "flat" or signals[1] == "flat", "bar 1 should be flat"


def test_derive_composite_signals_flat_when_nan_conditions():
    closes = np.arange(100.0, 120.0)
    sma = np.full(20, np.nan)  # never defined
    vote = np.full(20, 1.0)
    signals, position = kse.derive_composite_signals(closes, sma, vote)
    assert (position == 0).all(), "NaN sma must force flat"
    assert (signals == "flat").all()


# ---------------------------------------------------------------------------
# walk_forward_metrics
# ---------------------------------------------------------------------------

def test_walk_forward_metrics_directional_accuracy_vs_actual():
    closes = monotonic_closes(200, start=100.0, step=0.3)
    n = len(closes)
    vote = np.full(n, 1.0)  # always long
    position = np.ones(n)
    timestamps = pd.date_range("2024-01-01", periods=n, freq="1D", tz="UTC")

    m = kse.walk_forward_metrics(closes, position, vote, timestamps)

    # In a clean uptrend, always-long should have near-perfect directional acc
    assert m["directional_accuracy_pct"] > 90.0, "clean uptrend should be caught"
    assert m["net_return_pct"] > 0
    assert m["buy_hold_pct"] > 0
    assert m["evaluated_bars"] > 0
    assert m["evaluated_from"] <= m["evaluated_to"]


def test_walk_forward_metrics_fee_charged_on_entry():
    # Flat series -> no movement, but a single entry at bar 1 (the first bar
    # that is actually evaluated, since valid[0] is false) should still
    # leave a small negative net return equal to the fee.
    closes = np.full(100, 100.0)
    vote = np.full(100, 1.0)
    position = np.zeros(100)
    position[1] = 1  # enter at the first evaluated bar, flat afterwards
    timestamps = pd.date_range("2024-01-01", periods=100, freq="1D", tz="UTC")

    m = kse.walk_forward_metrics(closes, position, vote, timestamps, fee=0.001)
    assert abs(m["buy_hold_pct"]) < 1e-6, "flat series buy-hold should be ~0"
    assert m["net_return_pct"] < 0, "entry fee should cost money"
    assert abs(m["net_return_pct"] - (-0.1)) < 1e-6, "one 0.1% entry fee"


# ---------------------------------------------------------------------------
# process_series in dry-run mode (no Supabase, no torch)
# ---------------------------------------------------------------------------

def _fake_predictor(returned_df):
    """Stand-in predictor that returns prebuilt rows (as the real KronosPredictor
    would via predict_bars_walkforward) — but only for the eval window."""
    class FakePredictor:
        def predict(self, *a, **k):
            return returned_df
    return FakePredictor()


def test_process_series_dry_run_logic_only():
    # Patch data loading - returns synthetic OHLCV without touching Supabase.
    # (No pytest here: save/restore manually so the __main__ runner works too.)
    saved_lookback = kse.LOOKBACK
    saved_load = kse.load_ohlcv
    kse.LOOKBACK = 100
    closes = monotonic_closes(250, start=100.0, step=0.3)
    df = synth_df(closes)

    calls = {}
    def fake_load(supabase, symbol, timeframe):
        calls["symbol"] = symbol
        calls["timeframe"] = timeframe
        return df
    kse.load_ohlcv = fake_load

    try:
        res = kse.process_series(
            supabase=None, symbol="BTC-USDT", timeframe="1d",
            max_eval_bars=150, recent_bars=0, predictor=None, no_upload=True,
        )

        assert res["status"] == "dry-run"
        assert res["pred_rows"] > 0, "logic-only mode should still emit rows"
        assert res["sig_rows"] > 0
        assert res["metrics"]["evaluated_bars"] > 0
        assert calls["symbol"] == "BTC-USDT" and calls["timeframe"] == "1d"
        print(f"  dry-run rows: pred={res['pred_rows']} sig={res['sig_rows']} "
              f"dir_acc={res['metrics']['directional_accuracy_pct']:.1f}%")

        # Re-run with the shorter-window predictor: must NOT crash on shape
        pred_short = pd.DataFrame(
            {"close": closes[-150:]},
            index=df.index[-150:],
        )
        res2 = kse.process_series(
            supabase=None, symbol="BTC-USDT", timeframe="1d",
            max_eval_bars=150, recent_bars=0,
            predictor=_fake_predictor(pred_short), no_upload=True,
        )
        assert res2["status"] == "dry-run", f"got {res2['status']}"
    finally:
        kse.LOOKBACK = saved_lookback
        kse.load_ohlcv = saved_load


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import traceback

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failures = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception:
            failures += 1
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    if failures:
        print(f"\n{failures}/{len(tests)} tests FAILED")
        sys.exit(1)
    print(f"\nAll {len(tests)} tests PASSED")