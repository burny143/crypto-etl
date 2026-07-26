#!/usr/bin/env python3
"""
strategy_research.py — Strategy Research Engine v2.0

Fetches OHLCV data from Supabase, computes indicators, runs walk-forward
parameter sweeps across 8 strategy templates. Reports in-sample vs out-of-sample
performance so you can distinguish genuine edge from overfit.

Strategy templates:
  1. RSI Mean Reversion      oversold → long, overbought → short
  2. MACD Crossover          MACD crosses signal line
  3. Bollinger Bands         price touches lower/upper band
  4. EMA Crossover           fast/slow EMA trend following
  5. StochRSI                K crosses D at extremes
  6. Keltner Channel         price breaks upper/lower channel
  7. RSI + ADX Combo         RSI extremes filtered by trend strength
  8. RSI + Volume Combo      RSI extremes confirmed by volume spike

Walk-forward validation:
  - Splits data at train_pct (default 70/30)
  - Sweeps ALL parameter combos on training portion
  - Tests top K (default 5) Sharpe performers on held-out test portion
  - Flags each result as 'in_sample' or 'out_of_sample'
  - Reveals whether top training strategies hold up on unseen data

Usage:
    python strategy_research.py
    python strategy_research.py --symbols BTC-USDT,ETH-USDT
    python strategy_research.py --timeframes 1d,4h,1h
    python strategy_research.py --quick          (fewer param combos)
    python strategy_research.py --train-pct 0.7  (default)
    python strategy_research.py --top-k 5        (default)

Environment: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
"""

from __future__ import annotations

import argparse
import itertools
import math
import os
import sys
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import numpy as np
import pandas as pd
from supabase import create_client, Client


# ===============================================================================
# CONFIG
# ===============================================================================

ALL_SYMBOLS = [
    "BTC-USDT", "ETH-USDT", "XRP-USDT", "SOL-USDT", "BNB-USDT",
    "ADA-USDT", "DOGE-USDT", "AVAX-USDT", "DOT-USDT", "LINK-USDT",
    "UNI-USDT", "SHIB-USDT", "LTC-USDT", "BCH-USDT", "ATOM-USDT",
    "ETC-USDT", "XLM-USDT", "FIL-USDT", "TRX-USDT", "NEAR-USDT",
    "APT-USDT", "ARB-USDT", "OP-USDT", "SUI-USDT", "PEPE-USDT",
    "INJ-USDT", "TIA-USDT", "POL-USDT", "SEI-USDT", "STRK-USDT",
]
DEFAULT_TIMEFRAMES = ["1d", "4h", "1h"]

# ---------------------------------------------------------------------------
# Parameter grids — moderately wide to find real edge without exploding combos
# ---------------------------------------------------------------------------

RSI_GRID = {
    "period":        range(5, 26, 2),     # 11
    "oversold":      range(20, 45, 5),    #  5  (20,25,30,35,40)
    "overbought":    range(55, 86, 5),    #  7  (55,60,65,70,75,80,85)
}  # 385 combos

MACD_GRID = {
    "fast":          range(6, 22, 2),     #  8
    "slow":          range(18, 42, 3),    #  8
    "signal":        range(5, 15, 2),     #  5
}  # 320 combos

BB_GRID = {
    "period":        range(10, 32, 2),    # 11
    "std":           [1.5, 2.0, 2.5, 3.0, 3.5],
}  # 55 combos

EMA_GRID = {
    "fast":          range(3, 25, 2),     # 11
    "slow":          range(20, 60, 5),    #  8
}  # 88 combos

STOCH_RSI_GRID = {
    "period":        range(7, 22, 2),     #  8
    "smooth_k":      [3],
    "smooth_d":      [3],
    "oversold":      [15, 20, 25],
    "overbought":    [75, 80, 85],
}  # 72 combos

KC_GRID = {
    "period":        range(10, 32, 2),    # 11
    "mult":          [1.5, 2.0, 2.5, 3.0, 3.5],
}  # 55 combos

RSI_ADX_GRID = {
    "rsi_period":     [9, 14],
    "rsi_oversold":   [20, 25, 30, 35],
    "rsi_overbought": [65, 70, 75, 80],
    "adx_period":     [9, 14],
    "adx_threshold":  [20, 25, 30],
}  # 192 combos

RSI_VOL_GRID = {
    "rsi_period":     [9, 14],
    "rsi_oversold":   [20, 25, 30, 35],
    "rsi_overbought": [65, 70, 75, 80],
    "vol_period":     [15, 20, 25],
    "vol_mult":       [1.2, 1.5, 2.0, 3.0],
}  # 384 combos

# Hard cap on combos per strategy to keep runtime sane
MAX_COMBOS_PER_STRATEGY = 500


# ===============================================================================
# DATA
# ===============================================================================

def _supabase() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
    return create_client(url, key)


def load_ohlcv(supabase: Client, symbol: str, timeframe: str) -> pd.DataFrame | None:
    """Fetch OHLCV bars from Supabase, return sorted DataFrame with DatetimeIndex."""
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
        print(f"  [ERR] Supabase query failed: {e}")
        return None

    if not resp.data:
        return None

    df = pd.DataFrame(resp.data)
    if df.empty or len(df) < 100:
        return None

    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    df = df.set_index("datetime")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df.dropna(subset=["close"], inplace=True)
    return df.sort_index()


# ===============================================================================
# INDICATORS (pandas-only, no TA-Lib)
# ===============================================================================

def _sma(close: pd.Series, period: int) -> pd.Series:
    return close.rolling(window=period).mean()

def _ema(close: pd.Series, period: int) -> pd.Series:
    return close.ewm(span=period, adjust=False).mean()

def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def _macd(close: pd.Series, fast: int, slow: int, signal: int) -> pd.DataFrame:
    ef = close.ewm(span=fast, adjust=False).mean()
    es = close.ewm(span=slow, adjust=False).mean()
    macd_line = ef - es
    sig_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - sig_line
    return pd.DataFrame({"macd": macd_line, "signal": sig_line, "hist": hist})

def _bb(close: pd.Series, period: int, std: float) -> pd.DataFrame:
    mid = close.rolling(window=period).mean()
    sd = close.rolling(window=period).std()
    upper = mid + std * sd
    lower = mid - std * sd
    return pd.DataFrame({"upper": upper, "mid": mid, "lower": lower})

def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    h, l, c = high.astype(float), low.astype(float), close.astype(float)
    tr = pd.concat([
        (h - l).abs(),
        (h - c.shift()).abs(),
        (l - c.shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()

def _adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    h, l, c = high.astype(float), low.astype(float), close.astype(float)
    up = h.diff()
    down = -l.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=h.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=h.index)
    tr = pd.concat([(h - l).abs(), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()
    pdi = 100 * plus_dm.ewm(span=period, adjust=False).mean() / atr.replace(0, np.nan)
    mdi = 100 * minus_dm.ewm(span=period, adjust=False).mean() / atr.replace(0, np.nan)
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(span=period, adjust=False).mean()

def _obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    return (volume.astype(float) * np.sign(close.astype(float).diff())).fillna(0).cumsum()

def _stoch_rsi(close: pd.Series, period: int, smooth_k: int, smooth_d: int) -> pd.DataFrame:
    rsi = _rsi(close, period)
    min_r = rsi.rolling(window=period).min()
    max_r = rsi.rolling(window=period).max()
    stoch = 100 * (rsi - min_r) / (max_r - min_r).replace(0, np.nan)
    k = stoch.rolling(window=smooth_k).mean()
    d = k.rolling(window=smooth_d).mean()
    return pd.DataFrame({"k": k, "d": d})

def _vol_ratio(close: pd.Series, volume: pd.Series, period: int) -> pd.Series:
    vol = volume.astype(float)
    avg = vol.rolling(window=period).mean()
    return vol / avg.replace(0, np.nan)

def _kc(high: pd.Series, low: pd.Series, close: pd.Series, period: int, mult: float) -> pd.DataFrame:
    mid = close.ewm(span=period, adjust=False).mean()
    atr = _atr(high, low, close, period)
    return pd.DataFrame({"upper": mid + mult * atr, "mid": mid, "lower": mid - mult * atr})


# ===============================================================================
# SIGNAL GENERATORS — each returns pd.Series in {-1, 0, 1}
# ===============================================================================

def signal_rsi_reversion(df: pd.DataFrame, p: dict) -> pd.Series:
    rsi = _rsi(df["close"], p["period"])
    sig = pd.Series(0, index=df.index)
    sig[rsi < p["oversold"]] = 1
    sig[rsi > p["overbought"]] = -1
    return sig

def signal_macd_crossover(df: pd.DataFrame, p: dict) -> pd.Series:
    m = _macd(df["close"], p["fast"], p["slow"], p["signal"])
    macd, sig = m["macd"], m["signal"]
    sig_series = pd.Series(0, index=df.index)
    cross_above = (macd.shift(1) <= sig.shift(1)) & (macd > sig)
    cross_below = (macd.shift(1) >= sig.shift(1)) & (macd < sig)
    sig_series[cross_above] = 1
    sig_series[cross_below] = -1
    return sig_series

def signal_bb_reversion(df: pd.DataFrame, p: dict) -> pd.Series:
    b = _bb(df["close"], p["period"], p["std"])
    close = df["close"]
    sig_series = pd.Series(0, index=df.index)
    sig_series[close < b["lower"]] = 1
    sig_series[close > b["upper"]] = -1
    return sig_series

def signal_ema_crossover(df: pd.DataFrame, p: dict) -> pd.Series:
    fast = _ema(df["close"], p["fast"])
    slow = _ema(df["close"], p["slow"])
    sig_series = pd.Series(0, index=df.index)
    sig_series[fast > slow] = 1
    sig_series[fast < slow] = -1
    return sig_series

def signal_stoch_rsi(df: pd.DataFrame, p: dict) -> pd.Series:
    sd = _stoch_rsi(df["close"], p["period"], p["smooth_k"], p["smooth_d"])
    k, d = sd["k"], sd["d"]
    sig_series = pd.Series(0, index=df.index)
    long_cond = (k < p["oversold"]) & (k.shift(1) <= d.shift(1)) & (k > d)
    short_cond = (k > p["overbought"]) & (k.shift(1) >= d.shift(1)) & (k < d)
    sig_series[long_cond] = 1
    sig_series[short_cond] = -1
    return sig_series

def signal_kc_breakout(df: pd.DataFrame, p: dict) -> pd.Series:
    kc = _kc(df["high"], df["low"], df["close"], p["period"], p["mult"])
    close = df["close"]
    sig_series = pd.Series(0, index=df.index)
    sig_series[close > kc["upper"]] = 1
    sig_series[close < kc["lower"]] = -1
    return sig_series

def signal_rsi_adx(df: pd.DataFrame, p: dict) -> pd.Series:
    rsi = _rsi(df["close"], p["rsi_period"])
    adx = _adx(df["high"], df["low"], df["close"], p["adx_period"])
    sig_series = pd.Series(0, index=df.index)
    # Mean reversion in low-trend regimes
    long_cond = (rsi < p["rsi_oversold"]) & (adx < p["adx_threshold"])
    short_cond = (rsi > p["rsi_overbought"]) & (adx < p["adx_threshold"])
    sig_series[long_cond] = 1
    sig_series[short_cond] = -1
    # Trend-follow in high-trend regimes
    ema_fast = _ema(df["close"], 12)
    ema_slow = _ema(df["close"], 26)
    trend_long = (ema_fast > ema_slow) & (adx >= p["adx_threshold"])
    trend_short = (ema_fast < ema_slow) & (adx >= p["adx_threshold"])
    sig_series[trend_long] = 1
    sig_series[trend_short] = -1
    return sig_series

def signal_rsi_vol(df: pd.DataFrame, p: dict) -> pd.Series:
    rsi = _rsi(df["close"], p["rsi_period"])
    vr = _vol_ratio(df["close"], df["volume"], p["vol_period"])
    sig_series = pd.Series(0, index=df.index)
    long_cond = (rsi < p["rsi_oversold"]) & (vr > p["vol_mult"])
    short_cond = (rsi > p["rsi_overbought"]) & (vr > p["vol_mult"])
    sig_series[long_cond] = 1
    sig_series[short_cond] = -1
    return sig_series


# ===============================================================================
# STRATEGY REGISTRY
# ===============================================================================

@dataclass
class StrategyDef:
    name: str
    signal_fn: Callable
    param_grid: dict
    param_labels: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.param_labels = list(self.param_grid.keys())

STRATEGIES = [
    StrategyDef("rsi_reversion",  signal_rsi_reversion,   RSI_GRID),
    StrategyDef("macd_crossover", signal_macd_crossover,  MACD_GRID),
    StrategyDef("bb_reversion",   signal_bb_reversion,    BB_GRID),
    StrategyDef("ema_crossover",  signal_ema_crossover,   EMA_GRID),
    StrategyDef("stoch_rsi",      signal_stoch_rsi,        STOCH_RSI_GRID),
    StrategyDef("kc_breakout",    signal_kc_breakout,     KC_GRID),
    StrategyDef("rsi_adx_combo",  signal_rsi_adx,          RSI_ADX_GRID),
    StrategyDef("rsi_vol_combo",  signal_rsi_vol,          RSI_VOL_GRID),
]


# ===============================================================================
# BACKTESTER
# ===============================================================================

@dataclass
class Trade:
    entry_time: Any
    exit_time: Any
    side: str
    entry_price: float
    exit_price: float
    pnl_pct: float
    bars_held: int

@dataclass
class BacktestResult:
    strategy_name: str
    params: dict
    symbol: str
    timeframe: str
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    win_rate: float
    profit_factor: float
    trade_count: int
    avg_bars_held: float
    calmar_ratio: float
    validation: str = "in_sample"       # "in_sample" | "out_of_sample"
    data_start_date: str | None = None
    data_end_date: str | None = None
    data_bar_count: int = 0
    train_start_date: str | None = None
    train_end_date: str | None = None
    test_start_date: str | None = None
    test_end_date: str | None = None
    trades: list[Trade] = field(default_factory=list)


def backtest(df: pd.DataFrame, signal: pd.Series) -> BacktestResult | None:
    """
    Run a simple backtest given OHLCV data and a signal series in {-1, 0, 1}.
    
    Rules:
    - Signal  1 → enter/hold long
    - Signal -1 → enter/hold short
    - Signal  0 → flat (close any position)
    - Entry at next bar's open
    - Exit at next bar's open
    - No leverage, no fees
    """
    if df.empty or len(df) < 50:
        return None

    sig = signal.reindex(df.index).fillna(0).astype(int)
    close = df["close"]
    open_p = df["open"]

    position: int = 0
    entry_price: float = 0.0
    entry_idx: int = 0
    trades: list[Trade] = []
    equity_curve: list[float] = [10000.0]

    for i in range(1, len(df)):
        sig_now = sig.iloc[i]
        position_was = position

        if position != 0:
            if sig_now != position:
                exit_p = float(open_p.iloc[i])
                if position == 1:
                    pnl_pct = (exit_p - entry_price) / entry_price * 100
                else:
                    pnl_pct = (entry_price - exit_p) / entry_price * 100
                trades.append(Trade(
                    entry_time=df.index[entry_idx],
                    exit_time=df.index[i],
                    side="long" if position == 1 else "short",
                    entry_price=float(entry_price),
                    exit_price=exit_p,
                    pnl_pct=pnl_pct,
                    bars_held=i - entry_idx,
                ))
                equity_curve.append(equity_curve[-1] * (1 + pnl_pct / 100))
                position = 0

        if position == 0 and sig_now != 0:
            position = int(sig_now)
            entry_price = float(open_p.iloc[i])
            entry_idx = i

    # Close any open position at end
    if position != 0:
        exit_p = float(close.iloc[-1])
        if position == 1:
            pnl_pct = (exit_p - entry_price) / entry_price * 100
        else:
            pnl_pct = (entry_price - exit_p) / entry_price * 100
        trades.append(Trade(
            entry_time=df.index[entry_idx],
            exit_time=df.index[-1],
            side="long" if position == 1 else "short",
            entry_price=float(entry_price),
            exit_price=exit_p,
            pnl_pct=pnl_pct,
            bars_held=len(df) - 1 - entry_idx,
        ))
        equity_curve.append(equity_curve[-1] * (1 + pnl_pct / 100))

    if len(trades) < 2:
        return None

    eq = pd.Series(equity_curve)
    returns = eq.pct_change().dropna()
    total_return = (eq.iloc[-1] / eq.iloc[0] - 1) * 100

    if len(returns) > 1 and returns.std() > 0:
        sharpe = float(returns.mean() / returns.std() * np.sqrt(365))
    else:
        sharpe = 0.0

    peak = eq.expanding().max()
    dd = (eq - peak) / peak * 100
    max_dd = float(dd.min())

    wins = [t for t in trades if t.pnl_pct > 0]
    losses = [t for t in trades if t.pnl_pct <= 0]
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    gross_profit = sum(t.pnl_pct for t in wins) if wins else 0
    gross_loss = abs(sum(t.pnl_pct for t in losses)) if losses else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    avg_held = float(np.mean([t.bars_held for t in trades])) if trades else 0
    calmar = total_return / abs(max_dd) if max_dd != 0 else 0

    return BacktestResult(
        strategy_name="",
        params={},
        symbol="?",
        timeframe="?",
        total_return_pct=round(total_return, 2),
        sharpe_ratio=round(sharpe, 3),
        max_drawdown_pct=round(max_dd, 2),
        win_rate=round(win_rate, 1),
        profit_factor=round(profit_factor, 2) if profit_factor != float("inf") else 999.0,
        trade_count=len(trades),
        avg_bars_held=round(avg_held, 1),
        calmar_ratio=round(calmar, 2),
        data_start_date=str(df.index[0].date()),
        data_end_date=str(df.index[-1].date()),
        data_bar_count=len(df),
        trades=trades,
    )


# ===============================================================================
# WALK-FORWARD SWEEP
# ===============================================================================

def run_sweep(
    df: pd.DataFrame,
    strategy_def: StrategyDef,
    symbol: str,
    timeframe: str,
    train_pct: float = 0.7,
    top_k: int = 5,
    quick: bool = False,
) -> list[BacktestResult]:
    """
    Walk-forward parameter sweep:
    1. Split data into train (first train_pct) and test (remaining)
    2. Sweep all param combos on TRAIN data
    3. Pick top K by Sharpe from train results
    4. Test those K param sets on TEST data
    5. Return all results with validation flag

    Returns both training results (full sweep) and test results (top K only).
    """
    split_idx = int(len(df) * train_pct)
    train_df = df.iloc[:split_idx].copy()
    test_df = df.iloc[split_idx:].copy()

    train_start = str(train_df.index[0].date())
    train_end = str(train_df.index[-1].date())
    test_start = str(test_df.index[0].date())
    test_end = str(test_df.index[-1].date())

    # Build param combos
    grid = strategy_def.param_grid
    if quick:
        grid = {k: (v if not isinstance(v, range) else range(v.start, v.stop, max(1, (v.stop - v.start) // 3)))
                for k, v in grid.items()}
        grid = {k: list(v)[:3] for k, v in grid.items()}

    param_names = list(grid.keys())
    param_values = list(grid.values())
    total_combos = math.prod(len(v) for v in param_values)

    if total_combos > MAX_COMBOS_PER_STRATEGY:
        combos = list(itertools.product(*param_values))
        # Systematic sampling: take evenly spaced combos
        step = max(1, len(combos) // MAX_COMBOS_PER_STRATEGY)
        combos = combos[::step][:MAX_COMBOS_PER_STRATEGY]
    else:
        combos = list(itertools.product(*param_values))

    # --- Phase 1: Sweep all combos on TRAIN data ---
    train_results: list[BacktestResult] = []
    for combo in combos:
        params = dict(zip(param_names, combo))
        try:
            sig = strategy_def.signal_fn(train_df, params)
        except Exception:
            continue
        result = backtest(train_df, sig)
        if result is None:
            continue
        result.strategy_name = strategy_def.name
        result.params = params
        result.symbol = symbol
        result.timeframe = timeframe
        result.validation = "in_sample"
        result.train_start_date = train_start
        result.train_end_date = train_end
        result.test_start_date = test_start
        result.test_end_date = test_end
        train_results.append(result)

    # --- Phase 2: Test top K params on TEST data ---
    train_results.sort(key=lambda r: r.sharpe_ratio, reverse=True)
    top_train = train_results[:min(top_k, len(train_results))]

    test_results: list[BacktestResult] = []
    for tr in top_train:
        try:
            sig = strategy_def.signal_fn(test_df, tr.params)
        except Exception:
            continue
        result = backtest(test_df, sig)
        if result is None:
            continue
        result.strategy_name = strategy_def.name
        result.params = tr.params
        result.symbol = symbol
        result.timeframe = timeframe
        result.validation = "out_of_sample"
        result.train_start_date = train_start
        result.train_end_date = train_end
        result.test_start_date = test_start
        result.test_end_date = test_end
        test_results.append(result)

    return train_results + test_results


# ===============================================================================
# REPORTING
# ===============================================================================

def _safe(text: str) -> str:
    """Replace non-ASCII chars with ASCII equivalents for Windows console."""
    return text.replace("\u2192", "->").replace("\u2265", ">=")


def print_results(results: list[BacktestResult], top_n: int = 15):
    """Print ranked results, showing OOS performance for top IS strategies."""
    if not results:
        print("\n  No valid results found.")
        return

    train_results = [r for r in results if r.validation == "in_sample"]
    test_results = [r for r in results if r.validation == "out_of_sample"]

    # --- Top N by in-sample Sharpe, with their corresponding OOS result ---
    train_sorted = sorted(train_results, key=lambda r: r.sharpe_ratio, reverse=True)
    test_lookup = {(r.strategy_name, r.symbol, r.timeframe, str(sorted(r.params.items()))): r
                   for r in test_results}

    print(f"\n{'='*110}")
    print(f" TOP {top_n} STRATEGIES (ranked by in-sample Sharpe, with out-of-sample)")
    print(f"{'='*110}")
    header = (f"{'#':>3} {'Type':<18} {'Params':<30} {'Symbol':<10} {'TF':<3} "
              f"{'IS_Ret%':>7} {'IS_Sharpe':>8} {'OOS_Ret%':>8} {'OOS_Sharpe':>8} {'DD%':>6} {'Trades':>6}")
    print(header)
    print("-" * 110)

    for i, r in enumerate(train_sorted[:top_n]):
        # Find matching OOS result
        key = (r.strategy_name, r.symbol, r.timeframe, str(sorted(r.params.items())))
        oos = test_lookup.get(key)
        oos_ret = f"{oos.total_return_pct:>6.1f}%" if oos else "   N/A"
        oos_sharpe = f"{oos.sharpe_ratio:>7.3f}" if oos else "    N/A"

        param_str = ",".join(f"{k}={v}" for k, v in sorted(r.params.items()))
        if len(param_str) > 29:
            param_str = param_str[:26] + "..."

        print(
            f"{i+1:>3} {r.strategy_name:<18} {param_str:<30} {r.symbol:<10} {r.timeframe:<3} "
            f"{r.total_return_pct:>6.1f}% {r.sharpe_ratio:>8.3f} {oos_ret:>8} {oos_sharpe:>8} "
            f"{r.max_drawdown_pct:>5.1f}% {r.trade_count:>6}"
        )

    # --- Best per strategy type (show IS → OOS gap) ---
    print(f"\n{'='*110}")
    print(" BEST PER STRATEGY TYPE  (IS Sharpe -> OOS Sharpe)")
    print(f"{'='*110}")

    by_type: dict[str, list[BacktestResult]] = defaultdict(list)
    for r in train_results:
        by_type[r.strategy_name].append(r)

    for sname, sresults in sorted(by_type.items()):
        best = max(sresults, key=lambda r: r.sharpe_ratio)
        key = (best.strategy_name, best.symbol, best.timeframe, str(sorted(best.params.items())))
        oos = test_lookup.get(key)
        oos_info = f" -> OOS Sharpe={oos.sharpe_ratio:.3f}  Ret={oos.total_return_pct:.1f}%" if oos else " -> no OOS"
        print(f"  {sname:<18} IS Sharpe={best.sharpe_ratio:.3f}  Ret={best.total_return_pct:.1f}%  "
              f"Params=({','.join(f'{k}={v}' for k,v in sorted(best.params.items()))}){oos_info}")

    # --- OOS summary ---
    if test_results:
        valid_oos = [r for r in test_results if r.trade_count >= 10]
        if valid_oos:
            best_oos = max(valid_oos, key=lambda r: r.sharpe_ratio)
            print(f"\n{'='*110}")
            print(" BEST OUT-OF-SAMPLE (>=10 trades)")
            print(f"{'='*110}")
            print(f"  {best_oos.strategy_name:<18} Sharpe={best_oos.sharpe_ratio:.3f}  "
                  f"Ret={best_oos.total_return_pct:.1f}%  DD={best_oos.max_drawdown_pct:.1f}%  "
                  f"Trades={best_oos.trade_count}  {best_oos.symbol} [{best_oos.timeframe}]")
            print(f"  Params: {best_oos.params}")

    # --- All-time best IS ---
    best_is = train_sorted[0]
    print(f"\n{'='*110}")
    print(f" BEST IN-SAMPLE OVERALL")
    print(f"{'='*110}")
    print(f"  {best_is.strategy_name:<18} Sharpe={best_is.sharpe_ratio:.3f}  "
          f"Ret={best_is.total_return_pct:.1f}%  DD={best_is.max_drawdown_pct:.1f}%  "
          f"Trades={best_is.trade_count}  {best_is.symbol} [{best_is.timeframe}]")
    print(f"  Params: {best_is.params}")
    print(f"  Train: {best_is.train_start_date} -> {best_is.train_end_date} ({best_is.data_bar_count} bars)")
    key = (best_is.strategy_name, best_is.symbol, best_is.timeframe, str(sorted(best_is.params.items())))
    oos = test_lookup.get(key)
    if oos:
        print(f"  OOS:   Sharpe={oos.sharpe_ratio:.3f}  Ret={oos.total_return_pct:.1f}%  "
              f"DD={oos.max_drawdown_pct:.1f}%  Trades={oos.trade_count}")
    print(f"{'='*110}\n")


def export_results(results: list[BacktestResult], filepath: str = "strategy_results.csv"):
    """Export all results to CSV for further analysis."""
    rows = []
    for r in results:
        row = {
            "strategy": r.strategy_name,
            "symbol": r.symbol,
            "timeframe": r.timeframe,
            "validation": r.validation,
            **r.params,
            "return_pct": r.total_return_pct,
            "sharpe": r.sharpe_ratio,
            "max_dd_pct": r.max_drawdown_pct,
            "win_rate": r.win_rate,
            "profit_factor": r.profit_factor,
            "trade_count": r.trade_count,
            "avg_bars_held": r.avg_bars_held,
            "calmar": r.calmar_ratio,
        }
        # Only add train/test dates if populated
        if r.train_start_date:
            row["train_start"] = r.train_start_date
            row["train_end"] = r.train_end_date
            row["test_start"] = r.test_start_date
            row["test_end"] = r.test_end_date
        rows.append(row)
    if rows:
        pd.DataFrame(rows).to_csv(filepath, index=False)
        print(f"  Exported {len(rows)} results to {filepath}")


def export_results_to_supabase(results: list[BacktestResult], supabase: Client, run_id: str):
    """Write all strategy results to Supabase strategy_results table.

    Attempts to write walk-forward columns (validation, train/test dates).
    If those columns don't exist yet (V6 migration not applied), falls back
    gracefully to the core columns only.
    """
    if not results:
        return

    # Build rows with optional walk-forward columns
    rows = []
    for r in results:
        row = {
            "run_id": run_id,
            "strategy_name": r.strategy_name,
            "symbol": r.symbol,
            "timeframe": r.timeframe,
            "params": r.params,
            "total_return_pct": r.total_return_pct,
            "sharpe_ratio": r.sharpe_ratio,
            "max_drawdown_pct": r.max_drawdown_pct,
            "win_rate": r.win_rate,
            "profit_factor": r.profit_factor if r.profit_factor != 999.0 else None,
            "trade_count": r.trade_count,
            "avg_bars_held": r.avg_bars_held,
            "calmar_ratio": r.calmar_ratio,
            "data_start_date": r.data_start_date,
            "data_end_date": r.data_end_date,
            "data_bar_count": r.data_bar_count,
            # Walk-forward columns (may not exist yet — fallback handles)
            "validation": r.validation,
            "train_start_date": r.train_start_date,
            "train_end_date": r.train_end_date,
            "test_start_date": r.test_start_date,
            "test_end_date": r.test_end_date,
        }
        rows.append(row)

    # Try with walk-forward columns first, then fall back
    chunk_size = 200
    inserted = False
    for attempt in range(2):
        try:
            for i in range(0, len(rows), chunk_size):
                chunk = rows[i:i + chunk_size]
                supabase.table("strategy_results").insert(chunk).execute()
            inserted = True
            break
        except Exception as e:
            err_str = str(e).lower()
            if attempt == 0 and ("validation" in err_str or "train_start" in err_str or
                                 "does not exist" in err_str or "column" in err_str):
                # Walk-forward columns don't exist yet — strip them and retry
                print("  [INFO] Walk-forward columns not in schema - falling back to core columns")
                for row in rows:
                    row.pop("validation", None)
                    row.pop("train_start_date", None)
                    row.pop("train_end_date", None)
                    row.pop("test_start_date", None)
                    row.pop("test_end_date", None)
                # Encode validation type in params JSONB instead
                for r, row in zip(results, rows):
                    if r.validation == "out_of_sample":
                        row["params"]["_validation"] = "out_of_sample"
                continue
            else:
                print(f"  [WARN] Supabase insert failed: {e}")
                break

    if inserted:
        print(f"  Stored {len(rows)} results in Supabase (run_id={run_id[:8]}...)")


# ===============================================================================
# MAIN
# ===============================================================================

def main():
    parser = argparse.ArgumentParser(description="Strategy Research Engine v2.0")
    parser.add_argument("--symbols", default=",".join(ALL_SYMBOLS),
                        help="Comma-separated symbols (default: all 30)")
    parser.add_argument("--timeframes", default=",".join(DEFAULT_TIMEFRAMES),
                        help="Comma-separated timeframes (default: 1d,4h,1h)")
    parser.add_argument("--quick", action="store_true",
                        help="Smaller parameter grid for faster runs")
    parser.add_argument("--top-n", type=int, default=15,
                        help="Number of top strategies to show (default: 15)")
    parser.add_argument("--train-pct", type=float, default=0.7,
                        help="Fraction of data for training (default: 0.7)")
    parser.add_argument("--top-k", type=int, default=5,
                        help="Number of top params to test out-of-sample (default: 5)")
    parser.add_argument("--export", type=str, default="strategy_results.csv",
                        help="Export results CSV path")
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    timeframes = [t.strip() for t in args.timeframes.split(",") if t.strip()]

    print("=" * 60)
    print("  STRATEGY RESEARCH ENGINE  v2.0")
    print("  Walk-Forward Validation")
    print("=" * 60)
    print(f"\n  Symbols:    {len(symbols)} ({', '.join(symbols[:5])}...)")
    print(f"  Timeframes: {', '.join(timeframes)}")
    print(f"  Strategies: {len(STRATEGIES)}")
    print(f"  Quick mode: {'ON' if args.quick else 'OFF'}")
    print(f"  Train/Test: {int(args.train_pct*100)}/{int((1-args.train_pct)*100)} split, top-k={args.top_k}")
    print()

    supabase = _supabase()

    # Create research run
    run_id = str(uuid.uuid4())
    try:
        supabase.table("research_runs").insert({
            "run_id": run_id,
            "run_timestamp": datetime.now(timezone.utc).isoformat(),
            "symbols": symbols,
            "timeframes": timeframes,
            "total_variants": 0,
            "status": "running",
        }).execute()
    except Exception as e:
        print(f"  [WARN] Could not create research run: {e}")

    t_start = time.time()
    all_results: list[BacktestResult] = []
    total_sweeps = 0
    skipped_symbols = []

    for symbol in symbols:
        for timeframe in timeframes:
            print(f"-- {symbol} [{timeframe}] --")
            t0 = time.time()

            df = load_ohlcv(supabase, symbol, timeframe)
            if df is None:
                print(f"  SKIP - no data")
                skipped_symbols.append((symbol, timeframe))
                continue

            print(f"  Bars: {len(df)} ({df.index[0].date()} - {df.index[-1].date()})")
            min_bars = max(200, int(100 / args.train_pct))  # at least 100 in test set
            if len(df) < min_bars:
                print(f"  SKIP - too few bars for train/test split (need {min_bars})")
                skipped_symbols.append((symbol, timeframe))
                continue

            for strategy_def in STRATEGIES:
                results = run_sweep(
                    df, strategy_def, symbol, timeframe,
                    train_pct=args.train_pct, top_k=args.top_k, quick=args.quick,
                )
                all_results.extend(results)
                total_sweeps += len(results)

                if results:
                    train_only = [r for r in results if r.validation == "in_sample"]
                    test_only = [r for r in results if r.validation == "out_of_sample"]
                    best_train = max(train_only, key=lambda r: r.sharpe_ratio) if train_only else None
                    best_test = max(test_only, key=lambda r: r.sharpe_ratio) if test_only else None

                    line = f"  {strategy_def.name:<18} {len(train_only):>4} IS variants"
                    if best_train:
                        line += f"  best IS Sharpe={best_train.sharpe_ratio:.3f}"
                    if best_test:
                        line += f"  OOS Sharpe={best_test.sharpe_ratio:.3f}  Ret={best_test.total_return_pct:.1f}%"
                    print(line)

            elapsed = time.time() - t0
            print(f"  Done in {elapsed:.1f}s\n")

    duration = time.time() - t_start

    # Final report
    print(f"\n{'='*110}")
    print(f" SWEEP COMPLETE - {total_sweeps} variants across "
          f"{len(symbols)} symbols x {len(timeframes)} timeframes")
    print(f"{'='*110}")
    if skipped_symbols:
        print(f"  Skipped {len(skipped_symbols)} symbol/timeframe combos (no data):")
        for s, tf in skipped_symbols:
            print(f"    {s} [{tf}]")

    if all_results:
        print_results(all_results, top_n=args.top_n)
        export_results(all_results, args.export)
        export_results_to_supabase(all_results, supabase, run_id)

        try:
            supabase.table("research_runs").update({
                "total_variants": total_sweeps,
                "duration_seconds": round(duration, 1),
                "status": "completed",
            }).eq("run_id", run_id).execute()
        except Exception as e:
            print(f"  [WARN] Could not update research run: {e}")
    else:
        print("\n  No valid results. Check data availability.\n")
        try:
            supabase.table("research_runs").update({
                "status": "failed",
                "duration_seconds": round(duration, 1),
                "notes": "No valid results produced",
            }).eq("run_id", run_id).execute()
        except Exception:
            pass

    print(f"\n  Total time: {duration:.1f}s")


if __name__ == "__main__":
    main()
