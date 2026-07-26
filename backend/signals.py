"""
backend/signals.py — Signal engine API endpoints.

Allows configuring and running composite signals that combine multiple
indicator conditions into {-1, 0, 1} trading signals.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from supabase import Client

from .indicators import _load_ohlcv
from .main import get_supabase
from .signal_engine import SignalEngine, SignalCondition

logger = logging.getLogger(__name__)

router = APIRouter(tags=["signals"])

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

Operator = Literal["gt", "lt", "cross_above", "cross_below", "range"]
Side = Literal["long", "short"]


class ConditionConfig(BaseModel):
    indicator: str
    params: dict[str, Any] = Field(default_factory=dict)
    value_key: str | None = Field(None, description="Sub-key for multi-value indicators (bb: lower/upper/mid, macd: macd/signal/hist, stoch_rsi: k/d, kc: lower/upper/mid)")
    operator: Operator = "gt"
    value: float = 0.0
    value_low: float | None = None
    value_high: float | None = None
    side: Side = "long"


class SignalRequest(BaseModel):
    symbol: str
    timeframe: str
    conditions: list[ConditionConfig] = Field(..., min_length=1, max_length=10)
    logic: Literal["all", "any"] = "any"
    limit: int = Field(500, le=5000)


class SignalPoint(BaseModel):
    datetime: str
    signal: int  # -1, 0, 1
    indicators: dict[str, float | None]


class SignalResponse(BaseModel):
    symbol: str
    timeframe: str
    logic: str
    signals: list[SignalPoint]
    condition_count: int


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post("/signal")
async def compute_signal(
    req: SignalRequest,
    supabase: Client = Depends(get_supabase),
):
    """Compute a composite signal from indicator conditions.

    Accepts a set of conditions (indicator + params + operator + threshold),
    combines them using the specified logic ("all" = AND, "any" = OR),
    and returns {-1, 0, 1} signal values per bar.
    """
    # Build engine from request
    conditions = [
        SignalCondition(
            indicator=c.indicator,
            params=c.params,
            value_key=c.value_key,
            operator=c.operator,
            value=c.value,
            value_low=c.value_low,
            value_high=c.value_high,
            side=c.side,
        )
        for c in req.conditions
    ]

    engine = SignalEngine(conditions=conditions, logic=req.logic)

    # Load OHLCV data
    df = _load_ohlcv(supabase, req.symbol, req.timeframe)
    if df is None or df.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No OHLCV data found for {req.symbol} [{req.timeframe}]",
        )

    # Generate signal with indicator details
    result = engine.generate_with_details(df)
    signal = result["signal"]
    indicators = result["indicators"]

    # Build response (last `limit` bars)
    tail_idx = signal.dropna().tail(req.limit).index

    signals_out: list[dict[str, Any]] = []
    for dt in tail_idx:
        row: dict[str, Any] = {
            "datetime": pd.Timestamp(dt).isoformat(),
            "signal": int(signal.loc[dt]),
        }
        row["indicators"] = {
            name: (float(series.loc[dt]) if pd.notna(series.loc[dt]) else None)
            for name, series in indicators.items()
        }
        signals_out.append(row)

    return SignalResponse(
        symbol=req.symbol,
        timeframe=req.timeframe,
        logic=req.logic,
        signals=signals_out,
        condition_count=len(req.conditions),
    )
