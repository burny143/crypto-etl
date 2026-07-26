"""
backend/research.py — AI Research endpoints.

Provides endpoints for:
- Fetching AI research entries from the ``crypto_research`` table
- Generating basic technical analysis summaries
- Generating structured research by running the signal engine over recent data
- Pattern recognition endpoints (extensible for LLM integration)

This module follows patterns adapted from vibe-trading's research approach:
- Research is organized by symbol with report types (market_analysis, signal, etc.)
- Results are stored in the database for persistence
- Can be extended to call LLM APIs for generative analysis
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from supabase import Client

from .indicators import _load_ohlcv
from .main import get_supabase
from .signal_engine import (
    SignalEngine,
    SignalCondition,
    _compute_rsi,
    _compute_sma,
    _compute_ema,
    _compute_adx,
    _compute_atr,
    _compute_bb,
    _compute_obv,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["research"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ResearchEntryOut(BaseModel):
    id: int
    symbol: str
    report_type: str
    title: str
    summary: str
    details: dict[str, Any]
    sentiment: str | None
    confidence: float | None
    source: str
    created_at: str


class TechnicalSummary(BaseModel):
    symbol: str
    timeframe: str
    current_price: float
    price_change_24h: float | None
    indicators: dict[str, Any]
    support_resistance: dict[str, list[float]]
    summary: str


class GenerateRequest(BaseModel):
    symbol: str
    timeframe: str = "1d"


class GenerateResponse(BaseModel):
    id: int | None
    symbol: str
    report_type: str
    title: str
    summary: str
    details: dict[str, Any]
    sentiment: str | None
    confidence: float | None
    source: str
    created_at: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/research/{symbol}")
async def get_research(
    symbol: str,
    report_type: str | None = Query(None),
    limit: int = Query(20, le=100),
    supabase: Client = Depends(get_supabase),
):
    """Get AI research entries for a symbol."""
    try:
        query = (
            supabase.table("crypto_research")
            .select("*")
            .eq("symbol", symbol)
            .order("created_at", desc=True)
            .limit(limit)
        )
        if report_type:
            query = query.eq("report_type", report_type)
        resp = query.execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    return {"entries": resp.data or [], "symbol": symbol}


@router.get("/research/recent")
async def get_recent_research(
    limit: int = Query(10, le=50),
    supabase: Client = Depends(get_supabase),
):
    """Get most recent research entries across all symbols."""
    try:
        resp = (
            supabase.table("crypto_research")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    return {"entries": resp.data or []}


@router.get("/research/analysis/{symbol}/{timeframe}")
async def get_technical_analysis(
    symbol: str,
    timeframe: str = "1d",
    supabase: Client = Depends(get_supabase),
):
    """
    Generate a basic technical analysis summary for a symbol+timeframe.
    
    Computes key indicators and identifies support/resistance levels
    from historical data. Can be extended to call an LLM for richer analysis.
    """
    # Fetch recent OHLCV data
    try:
        resp = (
            supabase.table("crypto_historical")
            .select("datetime,open,high,low,close,volume")
            .eq("symbol", symbol)
            .eq("timeframe", timeframe)
            .order("datetime", desc=True)
            .limit(200)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    if not resp.data or len(resp.data) < 20:
        raise HTTPException(
            status_code=404,
            detail=f"Insufficient data for {symbol} [{timeframe}]",
        )

    df = pd.DataFrame(resp.data)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime")
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    volume = df["volume"].astype(float)

    # Current price
    current_price = float(close.iloc[-1])

    # 24h change (approximate — last bar vs bar before that)
    price_change = None
    if len(close) >= 2:
        price_change = ((float(close.iloc[-1]) - float(close.iloc[-2])) / float(close.iloc[-2])) * 100

    # SMA(20) and SMA(50)
    sma_20 = close.rolling(20).mean().iloc[-1]
    sma_50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else None

    # RSI(14)
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
    rs = gain / loss.replace(0, float("inf"))
    rsi = float((100 - (100 / (1 + rs))).iloc[-1]) if len(close) >= 14 else None

    # Support / Resistance: simple pivot points
    pivots = df.copy()
    pivots["is_high"] = high == high.rolling(5, center=True).max()
    pivots["is_low"] = low == low.rolling(5, center=True).min()
    resistance_levels = sorted(high[pivots["is_high"]].tail(5).tolist(), reverse=True)
    support_levels = sorted(low[pivots["is_low"]].tail(5).tolist())

    # Volume trend
    vol_sma = volume.rolling(20).mean().iloc[-1]
    vol_trend = "increasing" if volume.iloc[-1] > vol_sma * 1.2 else "decreasing" if volume.iloc[-1] < vol_sma * 0.8 else "neutral"

    # Generate summary text
    trend = "bullish" if sma_20 > close.iloc[-5] else "bearish" if sma_20 < close.iloc[-5] else "neutral"
    rsi_signal = "overbought" if rsi and rsi > 70 else "oversold" if rsi and rsi < 30 else "neutral"

    summary_parts = [
        f"{symbol} is trading at ${current_price:,.2f}.",
        f"Short-term trend (SMA20 vs 5 bars ago) is **{trend}**.",
    ]
    if rsi is not None:
        summary_parts.append(f"RSI(14) is {rsi:.1f} ({rsi_signal}).")
    if sma_50 is not None:
        cross = "above" if sma_20 > sma_50 else "below"
        summary_parts.append(f"SMA20 ({sma_20:.2f}) is {cross} SMA50 ({sma_50:.2f}).")
    summary_parts.append(f"Volume trend: {vol_trend}.")
    if resistance_levels:
        summary_parts.append(f"Near resistance: {', '.join(f'${r:,.2f}' for r in resistance_levels[:3])}.")
    if support_levels:
        summary_parts.append(f"Near support: {', '.join(f'${s:,.2f}' for s in support_levels[:3])}.")

    indicators = {
        "sma_20": round(float(sma_20), 2) if pd.notna(sma_20) else None,
        "sma_50": round(float(sma_50), 2) if sma_50 is not None and pd.notna(sma_50) else None,
        "rsi_14": round(rsi, 1) if rsi else None,
        "volume_trend": vol_trend,
    }

    return TechnicalSummary(
        symbol=symbol,
        timeframe=timeframe,
        current_price=current_price,
        price_change_24h=round(price_change, 2) if price_change else None,
        indicators=indicators,
        support_resistance={
            "resistance": [round(r, 2) for r in resistance_levels],
            "support": [round(s, 2) for s in support_levels],
        },
        summary=" ".join(summary_parts),
    )


# ---------------------------------------------------------------------------
# Research Generation (indicator → signal engine → structured research)
# ---------------------------------------------------------------------------


@router.post("/research/generate")
async def generate_research(
    req: GenerateRequest,
    supabase: Client = Depends(get_supabase),
):
    """
    Generate a structured research entry by running the signal engine
    over recent OHLCV data. Produces sentiment, confidence, entry/exit
    rationale, and stores the result in ``crypto_research``.
    """
    df = _load_ohlcv(supabase, req.symbol, req.timeframe)
    if df is None or len(df) < 30:
        raise HTTPException(
            status_code=404,
            detail=f"Insufficient OHLCV data for {req.symbol} [{req.timeframe}]",
        )

    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    volume = df["volume"].astype(float)

    current_price = float(close.iloc[-1])

    # --- Compute indicators for analysis ---
    sma_20 = _compute_sma(close, 20)
    sma_50 = _compute_sma(close, 50) if len(close) >= 50 else pd.Series(index=close.index, dtype=float)
    ema_12 = _compute_ema(close, 12)
    ema_26 = _compute_ema(close, 26)
    rsi = _compute_rsi(close, 14)
    adx = _compute_adx(high, low, close, 14)
    atr = _compute_atr(high, low, close, 14)
    bb = _compute_bb(close, 20, 2.0)
    obv = _compute_obv(close, volume)

    # --- Run signal engines ---
    # 1. RSI oversold/overbought reversal signals
    rsi_engine = SignalEngine(
        conditions=[
            SignalCondition("rsi", {"period": 14}, operator="lt", value=30, side="long"),
            SignalCondition("rsi", {"period": 14}, operator="gt", value=70, side="short"),
        ],
        logic="any",
    )
    rsi_signals = rsi_engine.generate(df)

    # 2. Trend-follow signals (EMA crossover + ADX confirmation)
    trend_long = (ema_12 > ema_26) & (adx > 25)
    trend_short = (ema_12 < ema_26) & (adx > 25)
    trend_signal = trend_long.astype(int) - trend_short.astype(int)

    # 3. Combined composite signal (voting)
    composite = rsi_signals + trend_signal
    composite = composite.clip(-1, 1)

    # --- Determine overall market assessment ---
    last_signal = int(composite.iloc[-1]) if not composite.empty else 0
    recent_signals = composite.tail(10)
    buy_count = int((recent_signals == 1).sum())
    sell_count = int((recent_signals == -1).sum())

    # Count recent signals (last 50 bars)
    sig_tail = composite.tail(50)
    total_buy = int((sig_tail == 1).sum())
    total_sell = int((sig_tail == -1).sum())
    total_neutral = int((sig_tail == 0).sum())

    # --- Trend direction ---
    last_sma_20 = float(sma_20.iloc[-1]) if pd.notna(sma_20.iloc[-1]) else current_price
    last_sma_50 = float(sma_50.iloc[-1]) if len(sma_50) > 0 and pd.notna(sma_50.iloc[-1]) else None
    last_rsi = float(rsi.iloc[-1]) if pd.notna(rsi.iloc[-1]) else 50
    last_adx = float(adx.iloc[-1]) if pd.notna(adx.iloc[-1]) else 0

    # Trend determination
    if last_sma_50 and last_sma_20 > last_sma_50 and last_adx > 25:
        trend = "bullish"
    elif last_sma_50 and last_sma_20 < last_sma_50 and last_adx > 25:
        trend = "bearish"
    elif last_sma_20 > close.tail(5).mean():
        trend = "mildly_bullish"
    elif last_sma_20 < close.tail(5).mean():
        trend = "mildly_bearish"
    else:
        trend = "neutral"

    # Volatility assessment
    last_atr = float(atr.iloc[-1]) if pd.notna(atr.iloc[-1]) else 0
    atr_pct = (last_atr / current_price) * 100 if current_price else 0
    volatility = "high" if atr_pct > 3 else "moderate" if atr_pct > 1.5 else "low"

    # Volume confirmation
    obv_series = obv
    obv_trend = "rising" if len(obv_series) > 10 and float(obv_series.iloc[-1]) > float(obv_series.iloc[-10]) else "falling"

    # --- Determine sentiment ---
    signal_strength = (total_buy - total_sell) / max(total_buy + total_sell + total_neutral, 1)
    if signal_strength > 0.3:
        sentiment = "bullish"
        confidence = min(0.5 + abs(signal_strength) * 0.5, 0.95)
    elif signal_strength < -0.3:
        sentiment = "bearish"
        confidence = min(0.5 + abs(signal_strength) * 0.5, 0.95)
    else:
        sentiment = "neutral"
        confidence = 0.3

    # Adjust confidence with ADX (strong trend = more confident)
    if last_adx > 30:
        confidence = min(confidence + 0.1, 0.95)
    elif last_adx < 20:
        confidence = max(confidence - 0.1, 0.1)

    # --- Entry / exit rationale ---
    entry_price = current_price
    atr_val = last_atr if last_atr > 0 else current_price * 0.02

    if sentiment == "bullish":
        stop_loss = round(entry_price - 1.5 * atr_val, 2)
        take_profit = round(entry_price + 3 * atr_val, 2)
        rationale = (
            f"Bullish bias with {int(confidence * 100)}% confidence. "
            f"Trend: {trend.replace('_', ' ')}, RSI: {last_rsi:.1f}, ADX: {last_adx:.1f}. "
            f"Suggested entry: ${entry_price:,.2f}, stop: ${stop_loss:,.2f}, target: ${take_profit:,.2f}. "
            f"Signal count (last 50 bars): {total_buy} buy / {total_sell} sell / {total_neutral} neutral."
        )
    elif sentiment == "bearish":
        stop_loss = round(entry_price + 1.5 * atr_val, 2)
        take_profit = round(entry_price - 3 * atr_val, 2)
        rationale = (
            f"Bearish bias with {int(confidence * 100)}% confidence. "
            f"Trend: {trend.replace('_', ' ')}, RSI: {last_rsi:.1f}, ADX: {last_adx:.1f}. "
            f"Suggested short entry: ${entry_price:,.2f}, stop: ${stop_loss:,.2f}, target: ${take_profit:,.2f}. "
            f"Signal count (last 50 bars): {total_buy} buy / {total_sell} sell / {total_neutral} neutral."
        )
    else:
        stop_loss = None
        take_profit = None
        rationale = (
            f"Neutral — no clear directional bias. "
            f"Trend: {trend.replace('_', ' ')}, RSI: {last_rsi:.1f}, ADX: {last_adx:.1f}. "
            f"Signals are mixed: {total_buy} buy / {total_sell} sell in last 50 bars."
        )

    # --- Build details payload ---
    details = {
        "trend": trend,
        "volatility": volatility,
        "volume_trend": obv_trend,
        "composite_signal": last_signal,
        "signal_strength": round(signal_strength, 3),
        "indicators": {
            "sma_20": round(last_sma_20, 2),
            "sma_50": round(last_sma_50, 2) if last_sma_50 else None,
            "rsi": round(last_rsi, 1),
            "adx": round(last_adx, 1),
            "atr": round(last_atr, 2),
            "atr_pct": round(atr_pct, 2),
        },
        "support_resistance": {
            "resistance": [round(float(bb["upper"].iloc[-1]), 2)] if pd.notna(bb["upper"].iloc[-1]) else [],
            "support": [round(float(bb["lower"].iloc[-1]), 2)] if pd.notna(bb["lower"].iloc[-1]) else [],
        },
        "signals": {
            "last_50_bars": {
                "buy": total_buy,
                "sell": total_sell,
                "neutral": total_neutral,
            },
        },
    }

    if stop_loss:
        details["entry"] = {"price": entry_price, "stop_loss": stop_loss, "take_profit": take_profit}

    # --- Store in database ---
    entry = {
        "symbol": req.symbol,
        "report_type": "ai_analysis",
        "title": f"{req.symbol} Technical Analysis — {trend.replace('_', ' ').title()}",
        "summary": rationale,
        "details": details,
        "sentiment": sentiment,
        "confidence": round(confidence, 2),
        "source": "signal_engine",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        resp = supabase.table("crypto_research").insert(entry).execute()
        created = resp.data[0] if resp.data else entry
    except Exception as e:
        logger.warning(f"Failed to store research entry: {e}")
        created = entry

    return GenerateResponse(
        id=created.get("id"),
        symbol=created.get("symbol", req.symbol),
        report_type=created.get("report_type", "ai_analysis"),
        title=created.get("title", f"{req.symbol} Technical Analysis"),
        summary=created.get("summary", rationale),
        details=created.get("details", details),
        sentiment=created.get("sentiment", sentiment),
        confidence=created.get("confidence", round(confidence, 2)),
        source=created.get("source", "signal_engine"),
        created_at=created.get("created_at", datetime.now(timezone.utc).isoformat()),
    )


# ---------------------------------------------------------------------------
# Extension point: LLM-powered research
# ---------------------------------------------------------------------------
# To add LLM-based research (following vibe-trading patterns):
#
# 1. Add an LLM client (e.g., openai, anthropic, or any langchain-compatible provider)
# 2. Create a prompt template that takes (symbol, timeframe, OHLCV stats) and
#    returns structured analysis (sentiment, key levels, pattern recognition, etc.)
# 3. Store results in the crypto_research table
# 4. Expose via a POST /research/generate endpoint
#
# Example structure:
#
# @router.post("/research/generate")
# async def generate_research(req: GenerateRequest):
#     ohlcv_data = fetch_ohlcv(req.symbol, req.timeframe)
#     indicators = compute_key_indicators(ohlcv_data)
#     prompt = build_research_prompt(req.symbol, ohlcv_data, indicators)
#     llm_response = await call_llm(prompt)
#     parsed = parse_llm_response(llm_response)
#     store_research(req.symbol, parsed)
#     return parsed
