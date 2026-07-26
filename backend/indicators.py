"""
backend/indicators.py — Technical indicator computation and caching.

Computes indicators server-side using pandas/numpy and caches results in
the Supabase ``indicators`` table. The frontend requests indicators by
(symbol, timeframe, indicator_name, parameters) and gets either cached
or freshly computed values.

Supported indicators: SMA, EMA, RSI, MACD, Bollinger Bands, VWAP,
ADX, ATR, OBV, Stoch RSI, Volume Ratio, Keltner Channels.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from supabase import Client

from .main import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(tags=["indicators"])

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class IndicatorRequest(BaseModel):
    symbol: str
    timeframe: str
    indicator_name: str = Field(
        ...,
        pattern=r"^(sma|ema|rsi|macd|bb|vwap|adx|atr|obv|stoch_rsi|vol_ratio|kc)$",
    )
    parameters: dict[str, Any] = Field(default_factory=dict)
    force_recompute: bool = False


class IndicatorResponse(BaseModel):
    symbol: str
    timeframe: str
    indicator_name: str
    parameters: dict[str, Any]
    values: list[dict[str, Any]]
    cached: bool


# ---------------------------------------------------------------------------
# Indicator implementations (pure pandas/numpy — no TA-Lib needed)
# ---------------------------------------------------------------------------

def _compute_sma(close: pd.Series, period: int = 20) -> pd.Series:
    return close.rolling(window=period).mean()


def _compute_ema(close: pd.Series, period: int = 20) -> pd.Series:
    return close.ewm(span=period, adjust=False).mean()


def _compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def _compute_macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return pd.DataFrame({"macd": macd_line, "signal": signal_line, "hist": histogram})


def _compute_bb(
    close: pd.Series, period: int = 20, std: float = 2.0
) -> pd.DataFrame:
    mid = close.rolling(window=period).mean()
    std_dev = close.rolling(window=period).std()
    upper = mid + std * std_dev
    lower = mid - std * std_dev
    return pd.DataFrame({"upper": upper, "mid": mid, "lower": lower})


def _compute_vwap(
    high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series
) -> pd.Series:
    typical_price = (high + low + close) / 3
    return (typical_price * volume).cumsum() / volume.cumsum()


def _compute_adx(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> pd.Series:
    """Average Directional Index — trend strength."""
    high_ = high.astype(float)
    low_ = low.astype(float)
    close_ = close.astype(float)

    up = high_.diff()
    down = -low_.diff()

    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=high.index)

    tr = pd.concat(
        [
            (high_ - low_).abs(),
            (high_ - close_.shift()).abs(),
            (low_ - close_.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr = tr.ewm(span=period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(span=period, adjust=False).mean() / atr.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(span=period, adjust=False).mean() / atr.replace(0, np.nan)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(span=period, adjust=False).mean()
    return adx


def _compute_atr(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> pd.Series:
    """Average True Range — volatility."""
    high_ = high.astype(float)
    low_ = low.astype(float)
    close_ = close.astype(float)

    tr = pd.concat(
        [
            (high_ - low_).abs(),
            (high_ - close_.shift()).abs(),
            (low_ - close_.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)

    return tr.ewm(span=period, adjust=False).mean()


def _compute_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume — volume confirmation."""
    close_ = close.astype(float)
    volume_ = volume.astype(float)
    obv = (volume_ * np.sign(close_.diff())).fillna(0).cumsum()
    return obv


def _compute_stoch_rsi(
    close: pd.Series, period: int = 14, smooth_k: int = 3, smooth_d: int = 3
) -> pd.DataFrame:
    """Stochastic RSI — momentum oscillator."""
    rsi = _compute_rsi(close, period)
    min_rsi = rsi.rolling(window=period).min()
    max_rsi = rsi.rolling(window=period).max()
    stoch = 100 * (rsi - min_rsi) / (max_rsi - min_rsi).replace(0, np.nan)
    k = stoch.rolling(window=smooth_k).mean()
    d = k.rolling(window=smooth_d).mean()
    return pd.DataFrame({"k": k, "d": d})


def _compute_vol_ratio(close: pd.Series, volume: pd.Series, period: int = 20) -> pd.Series:
    """Volume Ratio — current volume relative to rolling average."""
    volume_ = volume.astype(float)
    avg_vol = volume_.rolling(window=period).mean()
    return volume_ / avg_vol.replace(0, np.nan)


def _compute_kc(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 20,
    mult: float = 2.0,
) -> pd.DataFrame:
    """Keltner Channels — volatility-based envelope."""
    mid = close.ewm(span=period, adjust=False).mean()
    atr = _compute_atr(high, low, close, period)
    upper = mid + mult * atr
    lower = mid - mult * atr
    return pd.DataFrame({"upper": upper, "mid": mid, "lower": lower})


# ---------------------------------------------------------------------------
# Computation dispatch
# ---------------------------------------------------------------------------

INDICATOR_FUNCS = {
    "sma": lambda df, p: _compute_sma(df["close"], p.get("period", 20)),
    "ema": lambda df, p: _compute_ema(df["close"], p.get("period", 20)),
    "rsi": lambda df, p: _compute_rsi(df["close"], p.get("period", 14)),
    "macd": lambda df, p: _compute_macd(
        df["close"],
        p.get("fast", 12),
        p.get("slow", 26),
        p.get("signal", 9),
    ),
    "bb": lambda df, p: _compute_bb(
        df["close"], p.get("period", 20), p.get("std", 2.0)
    ),
    "vwap": lambda df, p: _compute_vwap(
        df["high"], df["low"], df["close"], df["volume"]
    ),
    "adx": lambda df, p: _compute_adx(
        df["high"], df["low"], df["close"], p.get("period", 14)
    ),
    "atr": lambda df, p: _compute_atr(
        df["high"], df["low"], df["close"], p.get("period", 14)
    ),
    "obv": lambda df, p: _compute_obv(df["close"], df["volume"]),
    "stoch_rsi": lambda df, p: _compute_stoch_rsi(
        df["close"],
        p.get("period", 14),
        p.get("smooth_k", 3),
        p.get("smooth_d", 3),
    ),
    "vol_ratio": lambda df, p: _compute_vol_ratio(
        df["close"], df["volume"], p.get("period", 20)
    ),
    "kc": lambda df, p: _compute_kc(
        df["high"], df["low"], df["close"],
        p.get("period", 20), p.get("mult", 2.0),
    ),
}


# ---------------------------------------------------------------------------
# Caching helpers
# ---------------------------------------------------------------------------

def _params_hash(parameters: dict[str, Any]) -> str:
    """Deterministic hash of indicator parameters."""
    raw = json.dumps(parameters, sort_keys=True)
    return hashlib.md5(raw.encode()).hexdigest()


def _load_ohlcv(supabase: Client, symbol: str, timeframe: str) -> pd.DataFrame | None:
    """Fetch OHLCV bars from Supabase, return sorted DataFrame."""
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
        logger.error(f"Supabase query failed: {e}")
        return None

    if not resp.data:
        return None

    df = pd.DataFrame(resp.data)
    if df.empty:
        return None

    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    df = df.set_index("datetime")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_index()


def _store_indicator_batch(
    supabase: Client,
    symbol: str,
    timeframe: str,
    indicator_name: str,
    parameters: dict[str, Any],
    results: pd.DataFrame | pd.Series,
):
    """Batch-upsert computed indicator values into the indicators table."""
    if results is None or (isinstance(results, pd.DataFrame) and results.empty):
        return
    if isinstance(results, pd.Series):
        results = results.to_frame("value")

    param_hash = _params_hash(parameters)
    param_json = json.dumps(parameters, sort_keys=True)

    records = []
    for dt, row in results.iterrows():
        if pd.isna(dt):
            continue
        if isinstance(row, pd.Series):
            # Multi-value indicator (MACD, BB)
            value_json = row.to_dict()
            value = None
        else:
            value_json = None
            value = float(row) if pd.notna(row) else None

        records.append({
            "symbol": symbol,
            "timeframe": timeframe,
            "datetime": pd.Timestamp(dt).isoformat(),
            "indicator_name": indicator_name,
            "parameters": param_json,
            "param_hash": param_hash,
            "value": value,
            "value_json": value_json,
        })

    if not records:
        return

    # Upsert in batches of 500
    batch_size = 500
    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        try:
            supabase.table("indicators").upsert(
                batch,
                on_conflict="symbol,timeframe,datetime,indicator_name,param_hash",
            ).execute()
        except Exception as e:
            logger.warning(f"Indicator upsert batch failed: {e}")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/indicators/{symbol}/{timeframe}/{indicator_name}")
async def get_indicator(
    symbol: str,
    timeframe: str,
    indicator_name: str,
    period: int | None = Query(None, description="Default period"),
    fast: int | None = Query(None),
    slow: int | None = Query(None),
    signal: int | None = Query(None),
    std: float | None = Query(None),
    smooth_k: int | None = Query(None),
    smooth_d: int | None = Query(None),
    mult: float | None = Query(None),
    force_recompute: bool = Query(False),
    limit: int = Query(500, le=5000),
    supabase: Client = Depends(get_supabase),
):
    """Get indicator values for a symbol+timeframe. Uses cache unless ``force_recompute``."""

    # Build parameters dict from query params
    params: dict[str, Any] = {}
    if indicator_name in ("sma", "ema"):
        params["period"] = period or (20 if indicator_name == "sma" else 20)
    elif indicator_name == "rsi":
        params["period"] = period or 14
    elif indicator_name == "macd":
        params["fast"] = fast or 12
        params["slow"] = slow or 26
        params["signal"] = signal or 9
    elif indicator_name == "bb":
        params["period"] = period or 20
        params["std"] = std or 2.0
    elif indicator_name == "vwap":
        params = {}
    elif indicator_name in ("adx", "atr"):
        params["period"] = period or 14
    elif indicator_name == "obv":
        params = {}
    elif indicator_name == "stoch_rsi":
        params["period"] = period or 14
        params["smooth_k"] = smooth_k or 3
        params["smooth_d"] = smooth_d or 3
    elif indicator_name == "vol_ratio":
        params["period"] = period or 20
    elif indicator_name == "kc":
        params["period"] = period or 20
        params["mult"] = mult or 2.0

    param_hash = _params_hash(params)

    # Check cache first
    if not force_recompute:
        try:
            resp = (
                supabase.table("indicators")
                .select("datetime,value,value_json")
                .eq("symbol", symbol)
                .eq("timeframe", timeframe)
                .eq("indicator_name", indicator_name)
                .eq("param_hash", param_hash)
                .order("datetime", desc=True)
                .limit(limit)
                .execute()
            )
            if resp.data and len(resp.data) > 0:
                values = sorted(resp.data, key=lambda r: r["datetime"])
                return IndicatorResponse(
                    symbol=symbol,
                    timeframe=timeframe,
                    indicator_name=indicator_name,
                    parameters=params,
                    values=values,
                    cached=True,
                )
        except Exception:
            pass

    # Compute from OHLCV
    df = _load_ohlcv(supabase, symbol, timeframe)
    if df is None or df.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No OHLCV data found for {symbol} [{timeframe}]",
        )

    func = INDICATOR_FUNCS.get(indicator_name)
    if not func:
        raise HTTPException(status_code=400, detail=f"Unknown indicator: {indicator_name}")

    result = func(df, params)

    # Cache the result
    _store_indicator_batch(supabase, symbol, timeframe, indicator_name, params, result)

    # Format response
    if isinstance(result, pd.Series):
        values = [
            {"datetime": ts.isoformat(), "value": float(v) if pd.notna(v) else None}
            for ts, v in result.dropna().tail(limit).items()
        ]
    else:
        values = [
            {
                "datetime": ts.isoformat(),
                **{col: float(v) if pd.notna(v) else None for col, v in row.items()},
            }
            for ts, row in result.dropna().tail(limit).iterrows()
        ]

    return IndicatorResponse(
        symbol=symbol,
        timeframe=timeframe,
        indicator_name=indicator_name,
        parameters=params,
        values=values,
        cached=False,
    )


@router.post("/indicators/batch")
async def batch_indicators(
    requests: list[IndicatorRequest],
    supabase: Client = Depends(get_supabase),
):
    """Compute multiple indicators in a single request."""
    results = []
    for req in requests:
        try:
            # Re-dispatch to the single-indicator logic
            resp = await get_indicator(
                symbol=req.symbol,
                timeframe=req.timeframe,
                indicator_name=req.indicator_name,
                force_recompute=req.force_recompute,
                supabase=supabase,
                **{k: v for k, v in req.parameters.items() if v is not None},
            )
            results.append(resp)
        except HTTPException as e:
            results.append({
                "error": True,
                "symbol": req.symbol,
                "indicator_name": req.indicator_name,
                "detail": e.detail,
            })
    return {"indicators": results}
