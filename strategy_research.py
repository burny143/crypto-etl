#!/usr/bin/env python3
"""
strategy_research.py ? Strategy Research Engine

Fetches OHLCV data from Supabase, computes indicators, and runs parameter sweeps
across strategy templates inspired by vibe-trading research patterns.
Reports best-performing strategies with full metrics.

Strategy templates implemented:
  1. RSI Mean Reversion     ? oversold ? long, overbought ? short
  2. MACD Crossover         ? MACD crosses signal line
  3. Bollinger Bands        ? price touches lower/upper band
  4. EMA Crossover          ? fast/slow EMA trend following
  5. StochRSI               ? K crosses D at extremes
  6. Keltner Channel        ? price breaks upper/lower channel
  7. RSI + ADX Combo        ? RSI extremes filtered by trend strength
  8. RSI + Volume Combo     ? RSI extremes confirmed by volume spike

Usage:
    python strategy_research.py
    python strategy_research.py --symbols BTC-USDT,ETH-USDT
    python strategy_research.py --timeframes 1d,4h
    python strategy_research.py --quick        (smaller parameter grid)
    python strategy_research.py --top-n 20

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

DEFAULT_SYMBOLS = [
    "BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT",
    "ADA-USDT", "DOGE-USDT", "AVAX-USDT", "DOT-USDT", "LINK-USDT",
]
DEFAULT_TIMEFRAMES = ["1d", "4h"]

# Strategy parameter grids
RSI_GRID = {
    "period":        range(7, 22, 2),
    "oversold":      range(20, 40, 5),
    "overbought":    range(60, 81, 5),
}

MACD_GRID = {
    "fast":          range(6, 16, 2),
    "slow":          range(20, 36, 3),
    "signal":        range(5, 13, 2),
}

BB_GRID = {
    "period":        range(15, 26, 2),
    "std":           [1.5, 2.0, 2.5, 3.0],
}

EMA_GRID = {
    "fast":          range(5, 21, 3),
    "slow":          range(25, 55, 5),
}

STOCH_RSI_GRID = {
    "period":        range(7, 22, 2),
    "smooth_k":      [3],
    "smooth_d":      [3],
    "oversold":      [15, 20, 25],
    "overbought":    [75, 80, 85],
}

KC_GRID = {
    "period":        range(15, 26, 2),
    "mult":          [1.5, 2.0, 2.5, 3.0],
}

RSI_ADX_GRID = {
    "rsi_period":    [14],
    "rsi_oversold":  [25, 30, 35],
    "rsi_overbought": [65, 70, 75],
    "adx_period":    [14],
    "adx_threshold": [20, 25],
}

RSI_VOL_GRID = {
    "rsi_period":    [14],
    "rsi_oversold":  [25, 30, 35],
    "rsi_overbought": [65, 70, 75],
    "vol_period":    [20],
    "vol_mult":      [1.5, 2.0],
}


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
# SIGNAL GENERATORS ? each returns pd.Series in {-1, 0, 1}
# ===============================================================================

def signal_rsi_reversion(df: pd.DataFrame, p: dict) -> pd.Series:
    """RSI mean reversion: oversold ? long (1), overbought ? short (-1)."""
    rsi = _rsi(df["close"], p["period"])
    sig = pd.Series(0, index=df.index)
    sig[rsi < p["oversold"]] = 1
    sig[rsi > p["overbought"]] = -1
    return sig

def signal_macd_crossover(df: pd.DataFrame, p: dict) -> pd.Series:
    """MACD crossover: MACD crosses above signal ? long, below ? short."""
    m = _macd(df["close"], p["fast"], p["slow"], p["signal"])
    macd, sig = m["macd"], m["signal"]
    sig_series = pd.Series(0, index=df.index)
    cross_above = (macd.shift(1) <= sig.shift(1)) & (macd > sig)
    cross_below = (macd.shift(1) >= sig.shift(1)) & (macd < sig)
    sig_series[cross_above] = 1
    sig_series[cross_below] = -1
    return sig_series

def signal_bb_reversion(df: pd.DataFrame, p: dict) -> pd.Series:
    """Bollinger Bands mean reversion: touch lower ? long, upper ? short."""
    b = _bb(df["close"], p["period"], p["std"])
    close = df["close"]
    sig_series = pd.Series(0, index=df.index)
    sig_series[close < b["lower"]] = 1
    sig_series[close > b["upper"]] = -1
    return sig_series

def signal_ema_crossover(df: pd.DataFrame, p: dict) -> pd.Series:
    """EMA crossover trend: fast > slow ? long, fast < slow ? short."""
    fast = _ema(df["close"], p["fast"])
    slow = _ema(df["close"], p["slow"])
    sig_series = pd.Series(0, index=df.index)
    sig_series[fast > slow] = 1
    sig_series[fast < slow] = -1
    return sig_series

def signal_stoch_rsi(df: pd.DataFrame, p: dict) -> pd.Series:
    """StochRSI: K crosses D below oversold ? long, above overbought ? short."""
    sd = _stoch_rsi(df["close"], p["period"], p["smooth_k"], p["smooth_d"])
    k, d = sd["k"], sd["d"]
    sig_series = pd.Series(0, index=df.index)
    # Long: K below oversold and K crosses above D
    long_cond = (k < p["oversold"]) & (k.shift(1) <= d.shift(1)) & (k > d)
    short_cond = (k > p["overbought"]) & (k.shift(1) >= d.shift(1)) & (k < d)
    sig_series[long_cond] = 1
    sig_series[short_cond] = -1
    return sig_series

def signal_kc_breakout(df: pd.DataFrame, p: dict) -> pd.Series:
    """Keltner Channel breakout: close > upper ? long, close < lower ? short."""
    kc = _kc(df["high"], df["low"], df["close"], p["period"], p["mult"])
    close = df["close"]
    sig_series = pd.Series(0, index=df.index)
    sig_series[close > kc["upper"]] = 1
    sig_series[close < kc["lower"]] = -1
    return sig_series

def signal_rsi_adx(df: pd.DataFrame, p: dict) -> pd.Series:
    """RSI mean reversion filtered by ADX trend strength."""
    rsi = _rsi(df["close"], p["rsi_period"])
    adx = _adx(df["high"], df["low"], df["close"], p["adx_period"])
    sig_series = pd.Series(0, index=df.index)
    # Long when oversold AND trend is weak (ADX low) ? mean reversion setup
    long_cond = (rsi < p["rsi_oversold"]) & (adx < p["adx_threshold"])
    short_cond = (rsi > p["rsi_overbought"]) & (adx < p["adx_threshold"])
    sig_series[long_cond] = 1
    sig_series[short_cond] = -1
    # When ADX is high, follow the trend instead
    ema_fast = _ema(df["close"], 12)
    ema_slow = _ema(df["close"], 26)
    trend_long = (ema_fast > ema_slow) & (adx >= p["adx_threshold"])
    trend_short = (ema_fast < ema_slow) & (adx >= p["adx_threshold"])
    sig_series[trend_long] = 1
    sig_series[trend_short] = -1
    return sig_series

def signal_rsi_vol(df: pd.DataFrame, p: dict) -> pd.Series:
    """RSI extremes confirmed by volume spike."""
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
    side: str          # "long" or "short"
    entry_price: float
    exit_price: float
    pnl_pct: float     # percentage return
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
    data_start_date: str | None = None
    data_end_date: str | None = None
    data_bar_count: int = 0
    trades: list[Trade] = field(default_factory=list)


def backtest(df: pd.DataFrame, signal: pd.Series) -> BacktestResult | None:
    """
    Run a simple backtest given OHLCV data and a signal series in {-1, 0, 1}.
    
    Rules:
    - Signal 1  ? enter/hold long
    - Signal -1 ? enter/hold short
    - Signal 0  ? flat (close any position)
    - Entry at next bar's open
    - Exit at next bar's open
    - No leverage, no fees (for comparison; can be added later)
    """
    if df.empty or len(df) < 50:
        return None

    # Align signal to data
    sig = signal.reindex(df.index).fillna(0).astype(int)
    close = df["close"]
    open_p = df["open"]

    position: int = 0  # 0 flat, 1 long, -1 short
    entry_price: float = 0.0
    entry_idx: int = 0
    trades: list[Trade] = []
    equity_curve: list[float] = [10000.0]  # start at 10k

    for i in range(1, len(df)):
        sig_now = sig.iloc[i]
        prev_sig = sig.iloc[i - 1]

        if position != 0:
            # Check for exit: signal changes to opposite or flat
            if sig_now != position:
                # Close at today's open (next bar after signal)
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
            # Enter new position at today's open
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

    # --- Metrics ---
    eq = pd.Series(equity_curve)
    returns = eq.pct_change().dropna()

    total_return = (eq.iloc[-1] / eq.iloc[0] - 1) * 100

    # Sharpe (annualized, 365 for crypto)
    if len(returns) > 1 and returns.std() > 0:
        sharpe = float(returns.mean() / returns.std() * np.sqrt(365))
    else:
        sharpe = 0.0

    # Max drawdown
    peak = eq.expanding().max()
    dd = (eq - peak) / peak * 100
    max_dd = float(dd.min())

    # Win rate & profit factor
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
        symbol=df.attrs.get("symbol", "?"),
        timeframe=df.attrs.get("timeframe", "?"),
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
# SWEEP
# ===============================================================================

def run_sweep(
    df: pd.DataFrame,
    strategy_def: StrategyDef,
    symbol: str,
    timeframe: str,
    quick: bool = False,
) -> list[BacktestResult]:
    """Run parameter sweep for a single strategy on a single dataset."""
    results: list[BacktestResult] = []
    grid = strategy_def.param_grid

    if quick:
        # Smaller grid: take at most 3 values per param
        grid = {k: (v if not isinstance(v, range) else range(v.start, v.stop, max(1, (v.stop - v.start) // 3)))
                for k, v in grid.items()}
        grid = {k: list(v)[:3] for k, v in grid.items()}

    param_names = list(grid.keys())
    param_values = list(grid.values())
    total_combos = math.prod(len(v) for v in param_values)

    if total_combos > 500:
        print(f"  Sweep: {total_combos} combos ? limiting to 500")
        # Take first 500 combos
        sample = list(itertools.product(*param_values))[:500]
    else:
        sample = list(itertools.product(*param_values))

    for combo in sample:
        params = dict(zip(param_names, combo))
        try:
            sig = strategy_def.signal_fn(df, params)
        except Exception:
            continue

        result = backtest(df, sig)
        if result is None:
            continue

        result.strategy_name = strategy_def.name
        result.params = params
        result.symbol = symbol
        result.timeframe = timeframe
        results.append(result)

    return results


# ===============================================================================
# REPORTING
# ===============================================================================

def print_results(results: list[BacktestResult], top_n: int = 15):
    """Print ranked results grouped by strategy type."""
    if not results:
        print("\n  No valid results found.")
        return

    # Sort by Sharpe
    sorted_results = sorted(results, key=lambda r: r.sharpe_ratio, reverse=True)

    print(f"\n{'='*90}")
    print(f" TOP {top_n} STRATEGIES (ranked by Sharpe ratio)")
    print(f"{'='*90}")

    header = f"{'#':>3} {'Type':<18} {'Params':<36} {'Symbol':<12} {'TF':<4} {'Ret%':>7} {'Sharpe':>7} {'DD%':>7} {'WR%':>6} {'PF':>6} {'Trades':>6}"
    print(header)
    print("-" * 90)

    for i, r in enumerate(sorted_results[:top_n]):
        param_str = ",".join(f"{k}={v}" for k, v in sorted(r.params.items()))
        if len(param_str) > 35:
            param_str = param_str[:32] + "..."
        print(
            f"{i+1:>3} {r.strategy_name:<18} {param_str:<36} {r.symbol:<12} {r.timeframe:<4} "
            f"{r.total_return_pct:>6.1f}% {r.sharpe_ratio:>7.3f} {r.max_drawdown_pct:>6.1f}% "
            f"{r.win_rate:>5.1f}% {r.profit_factor:>6.2f} {r.trade_count:>6}"
        )

    # --- Best per strategy type ---
    print(f"\n{'='*90}")
    print(f" BEST PER STRATEGY TYPE")
    print(f"{'='*90}")

    by_type: dict[str, list[BacktestResult]] = defaultdict(list)
    for r in results:
        by_type[r.strategy_name].append(r)

    for sname, sresults in sorted(by_type.items()):
        best = max(sresults, key=lambda r: r.sharpe_ratio)
        print(f"  {sname:<18} Sharpe={best.sharpe_ratio:.3f}  Ret={best.total_return_pct:.1f}%  "
              f"DD={best.max_drawdown_pct:.1f}%  params=({','.join(f'{k}={v}' for k,v in sorted(best.params.items()))})")

    # --- All-time best ---
    best_overall = sorted_results[0]
    print(f"\n{'='*90}")
    print(f" BEST OVERALL: {best_overall.strategy_name}")
    print(f"   Symbol:     {best_overall.symbol} [{best_overall.timeframe}]")
    print(f"   Params:     {best_overall.params}")
    print(f"   Return:     {best_overall.total_return_pct:.1f}%")
    print(f"   Sharpe:     {best_overall.sharpe_ratio:.3f}")
    print(f"   Max DD:     {best_overall.max_drawdown_pct:.1f}%")
    print(f"   Win Rate:   {best_overall.win_rate:.1f}%")
    print(f"   Profit Fac: {best_overall.profit_factor:.2f}")
    print(f"   Trades:     {best_overall.trade_count}")
    print(f"   Avg Hold:   {best_overall.avg_bars_held:.0f} bars")
    print(f"{'='*90}\n")


def export_results(results: list[BacktestResult], filepath: str = "strategy_results.csv"):
    """Export all results to CSV for further analysis."""
    rows = []
    for r in results:
        rows.append({
            "strategy": r.strategy_name,
            "symbol": r.symbol,
            "timeframe": r.timeframe,
            **r.params,
            "return_pct": r.total_return_pct,
            "sharpe": r.sharpe_ratio,
            "max_dd_pct": r.max_drawdown_pct,
            "win_rate": r.win_rate,
            "profit_factor": r.profit_factor,
            "trade_count": r.trade_count,
            "avg_bars_held": r.avg_bars_held,
            "calmar": r.calmar_ratio,
        })
    pd.DataFrame(rows).to_csv(filepath, index=False)
    print(f"  Exported {len(rows)} results to {filepath}")


def export_results_to_supabase(results: list[BacktestResult], supabase: Client, run_id: str):
    """Write all strategy results to Supabase strategy_results table."""
    if not results:
        return

    # Batch insert in chunks of 200
    rows = []
    for r in results:
        rows.append({
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
        })

    chunk_size = 200
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i:i + chunk_size]
        try:
            supabase.table("strategy_results").insert(chunk).execute()
        except Exception as e:
            print(f"  [WARN] Supabase insert failed (chunk {i//chunk_size}): {e}")

    print(f"  Stored {len(rows)} results in Supabase (run_id={run_id[:8]}...)")


# ===============================================================================
# MAIN
# ===============================================================================

def main():
    parser = argparse.ArgumentParser(description="Strategy Research Engine")
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS),
                        help="Comma-separated symbols (default: all)")
    parser.add_argument("--timeframes", default=",".join(DEFAULT_TIMEFRAMES),
                        help="Comma-separated timeframes (default: 1d,4h)")
    parser.add_argument("--quick", action="store_true",
                        help="Smaller parameter grid for faster runs")
    parser.add_argument("--top-n", type=int, default=15,
                        help="Number of top strategies to show (default: 15)")
    parser.add_argument("--export", type=str, default="strategy_results.csv",
                        help="Export results CSV path (default: strategy_results.csv)")
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    timeframes = [t.strip() for t in args.timeframes.split(",") if t.strip()]

    print("=" * 60)
    print("  STRATEGY RESEARCH ENGINE  v1.0")
    print("=" * 60)
    print(f"\n  Symbols:    {', '.join(symbols)}")
    print(f"  Timeframes: {', '.join(timeframes)}")
    print(f"  Strategies: {len(STRATEGIES)}")
    print(f"  Quick mode: {'ON' if args.quick else 'OFF'}")
    print()

    supabase = _supabase()

    # Create research run record
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

    for symbol in symbols:
        for timeframe in timeframes:
            print(f"-- {symbol} [{timeframe}] --")
            t0 = time.time()

            df = load_ohlcv(supabase, symbol, timeframe)
            if df is None:
                print(f"  SKIP - no data (need >= 50 bars)")
                continue

            # Store metadata
            df.attrs["symbol"] = symbol
            df.attrs["timeframe"] = timeframe
            print(f"  Bars: {len(df)} ({df.index[0].date()} - {df.index[-1].date()})")

            for strategy_def in STRATEGIES:
                results = run_sweep(df, strategy_def, symbol, timeframe, quick=args.quick)
                all_results.extend(results)
                total_sweeps += len(results)
                if results:
                    best = max(results, key=lambda r: r.sharpe_ratio)
                    print(f"  {strategy_def.name:<18} {len(results):>4} variants  "
                          f"best Sharpe={best.sharpe_ratio:.3f}  Ret={best.total_return_pct:.1f}%")

            elapsed = time.time() - t0
            print(f"  Done in {elapsed:.1f}s\n")

    duration = time.time() - t_start

    # Final report
    print(f"\n{'='*90}")
    print(f" SWEEP COMPLETE - {total_sweeps} strategy variants tested across "
          f"{len(symbols)} symbols x {len(timeframes)} timeframes")
    print(f"{'='*90}")

    if all_results:
        print_results(all_results, top_n=args.top_n)
        export_results(all_results, args.export)
        export_results_to_supabase(all_results, supabase, run_id)

        # Update research run as completed
        try:
            supabase.table("research_runs").update({
                "total_variants": total_sweeps,
                "duration_seconds": round(duration, 1),
                "status": "completed",
            }).eq("run_id", run_id).execute()
        except Exception as e:
            print(f"  [WARN] Could not update research run: {e}")
    else:
        print("\n  No valid results. Check data availability and Supabase connection.\n")
        try:
            supabase.table("research_runs").update({
                "status": "failed",
                "duration_seconds": round(duration, 1),
                "notes": "No valid results produced",
            }).eq("run_id", run_id).execute()
        except Exception:
            pass


if __name__ == "__main__":
    main()
