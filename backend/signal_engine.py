"""
backend/signal_engine.py — Composite signal generation from indicator rules.

Adapted from vibe-trading's SignalEngine contract: ``generate(data) -> signals``.
Returns signals in {-1, 0, 1} (short / neutral / long) by combining multiple
indicator-based conditions via configurable logic.

Condition types (operator):
  - ``gt``   – indicator value > threshold
  - ``lt``   – indicator value < threshold
  - ``cross_above`` – indicator crosses above threshold (previous ≤, current >)
  - ``cross_below`` – indicator crosses below threshold (previous ≥, current <)
  - ``range`` – threshold_low < indicator < threshold_high

Example config:
  {
    "conditions": [
      {"indicator": "rsi", "params": {"period": 14}, "operator": "lt", "value": 30, "side": "long"},
      {"indicator": "rsi", "params": {"period": 14}, "operator": "gt", "value": 70, "side": "short"}
    ],
    "logic": "any"   # "all" -> all active conditions must fire on same side
  }
"""

from __future__ import annotations

import logging
from typing import Any, Literal

import numpy as np
import pandas as pd

from .indicators import (
    _compute_adx,
    _compute_atr,
    _compute_bb,
    _compute_ema,
    _compute_kc,
    _compute_macd,
    _compute_obv,
    _compute_rsi,
    _compute_sma,
    _compute_stoch_rsi,
    _compute_vol_ratio,
    _compute_vwap,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Condition model
# ---------------------------------------------------------------------------

Operator = Literal["gt", "lt", "cross_above", "cross_below", "range"]
Side = Literal["long", "short"]


class SignalCondition:
    """A single condition that contributes to a signal.

    For multi-value indicators (bb, macd, stoch_rsi, kc), use ``value_key``
    to select the sub-column (e.g. "upper", "lower", "k", "d", "macd", "hist").

    Compares the indicator value to a constant ``value`` threshold using
    the specified ``operator``.
    """

    def __init__(
        self,
        indicator: str,
        params: dict[str, Any] | None = None,
        value_key: str | None = None,
        operator: Operator = "gt",
        value: float = 0.0,
        value_low: float | None = None,
        value_high: float | None = None,
        side: Side = "long",
    ):
        self.indicator = indicator
        self.params = params or {}
        self.value_key = value_key
        self.operator = operator
        self.value = value
        self.value_low = value_low
        self.value_high = value_high
        self.side = side

    def evaluate(self, indicator_series: pd.Series) -> pd.Series:
        """Return boolean Series where condition is true."""
        if self.operator == "gt":
            return indicator_series > self.value
        elif self.operator == "lt":
            return indicator_series < self.value
        elif self.operator == "cross_above":
            prev = indicator_series.shift(1)
            return (prev <= self.value) & (indicator_series > self.value)
        elif self.operator == "cross_below":
            prev = indicator_series.shift(1)
            return (prev >= self.value) & (indicator_series < self.value)
        elif self.operator == "range":
            return (indicator_series > self.value_low) & (indicator_series < self.value_high)
        else:
            raise ValueError(f"Unknown operator: {self.operator}")


# ---------------------------------------------------------------------------
# Signal Engine
# ---------------------------------------------------------------------------

INDICATOR_COMPUTERS: dict[str, callable] = {
    "sma": lambda df, p: _compute_sma(df["close"], p.get("period", 20)),
    "ema": lambda df, p: _compute_ema(df["close"], p.get("period", 20)),
    "rsi": lambda df, p: _compute_rsi(df["close"], p.get("period", 14)),
    "macd": lambda df, p: _compute_macd(
        df["close"], p.get("fast", 12), p.get("slow", 26), p.get("signal", 9)
    ),
    "bb": lambda df, p: _compute_bb(
        df["close"], p.get("period", 20), p.get("std", 2.0)
    ),
    "vwap": lambda df, p: _compute_vwap(df["high"], df["low"], df["close"], df["volume"]),
    "adx": lambda df, p: _compute_adx(df["high"], df["low"], df["close"], p.get("period", 14)),
    "atr": lambda df, p: _compute_atr(df["high"], df["low"], df["close"], p.get("period", 14)),
    "obv": lambda df, p: _compute_obv(df["close"], df["volume"]),
    "stoch_rsi": lambda df, p: _compute_stoch_rsi(
        df["close"], p.get("period", 14), p.get("smooth_k", 3), p.get("smooth_d", 3)
    ),
    "vol_ratio": lambda df, p: _compute_vol_ratio(
        df["close"], df["volume"], p.get("period", 20)
    ),
    "kc": lambda df, p: _compute_kc(
        df["high"], df["low"], df["close"], p.get("period", 20), p.get("mult", 2.0)
    ),
}


def _extract_series(
    result: pd.Series | pd.DataFrame, value_key: str | None
) -> pd.Series | None:
    """Extract a single pd.Series from an indicator result.

    If result is a DataFrame and value_key is given, return that column.
    If result is a Series, return it directly.
    If result is a DataFrame and no value_key, return None (ambiguous).
    """
    if isinstance(result, pd.Series):
        return result
    if isinstance(result, pd.DataFrame):
        if value_key and value_key in result.columns:
            return result[value_key]
        # Default: return first column
        return result.iloc[:, 0]
    return None


class SignalEngine:
    """Composite signal engine combining indicator conditions.

    Adapted from vibe-trading's contract: ``generate(ohlcv_df) -> signal_series``.
    Returns signals in {-1, 0, 1}.

    Attributes:
        conditions: List of SignalCondition rules.
        logic: "all" requires all conditions on the same side to fire;
               "any" triggers on the first matching condition.
    """

    def __init__(
        self,
        conditions: list[SignalCondition] | None = None,
        logic: Literal["all", "any"] = "any",
    ):
        self.conditions = conditions or []
        self.logic = logic

    def add_condition(self, condition: SignalCondition) -> None:
        self.conditions.append(condition)

    def generate(self, df: pd.DataFrame) -> pd.Series:
        """Compute composite signal for a single OHLCV DataFrame.

        Args:
            df: OHLCV DataFrame with open/high/low/close/volume columns.

        Returns:
            pd.Series with values in {-1, 0, 1}, same index as df.
        """
        if df.empty:
            return pd.Series(dtype=int)

        long_conditions: list[pd.Series] = []
        short_conditions: list[pd.Series] = []

        for cond in self.conditions:
            indicator_series = self._compute_indicator(df, cond)
            if indicator_series is None:
                continue
            result = cond.evaluate(indicator_series)
            if cond.side == "long":
                long_conditions.append(result)
            else:
                short_conditions.append(result)

        # Combine
        if self.logic == "all":
            long_signal = (
                pd.concat(long_conditions, axis=1).all(axis=1) if long_conditions
                else pd.Series(False, index=df.index)
            )
            short_signal = (
                pd.concat(short_conditions, axis=1).all(axis=1) if short_conditions
                else pd.Series(False, index=df.index)
            )
        else:
            long_signal = (
                pd.concat(long_conditions, axis=1).any(axis=1) if long_conditions
                else pd.Series(False, index=df.index)
            )
            short_signal = (
                pd.concat(short_conditions, axis=1).any(axis=1) if short_conditions
                else pd.Series(False, index=df.index)
            )

        # A bar can't be both long and short — long wins on conflict
        signal = long_signal.astype(int) - short_signal.astype(int)
        signal = signal.clip(-1, 1)
        return signal

    def generate_with_details(self, df: pd.DataFrame) -> dict[str, Any]:
        """Generate signal and return intermediate indicator values for debugging.

        Returns:
            dict with "signal" (pd.Series), "indicator_values" (dict of name->pd.Series).
        """
        signal = self.generate(df)
        indicators: dict[str, pd.Series] = {}
        for cond in self.conditions:
            key = f"{cond.indicator}({_params_str(cond.params)})"
            if key not in indicators:
                val = self._compute_indicator(df, cond)
                if val is not None:
                    indicators[key] = val
        return {"signal": signal, "indicators": indicators}

    def _compute_indicator(
        self, df: pd.DataFrame, cond: SignalCondition
    ) -> pd.Series | None:
        func = INDICATOR_COMPUTERS.get(cond.indicator)
        if func is None:
            logger.warning(f"Unknown indicator for signal: {cond.indicator}")
            return None
        try:
            result = func(df, cond.params)
            return _extract_series(result, cond.value_key)
        except Exception as e:
            logger.warning(f"Failed to compute {cond.indicator} for signal: {e}")
            return None


def _params_str(params: dict[str, Any]) -> str:
    return ",".join(f"{k}={v}" for k, v in sorted(params.items()))


# ---------------------------------------------------------------------------
# Convenience: build common signal configs
# ---------------------------------------------------------------------------


def rsi_oversold_signal(
    rsi_period: int = 14, rsi_threshold: float = 30
) -> SignalEngine:
    """Oversold bounce: RSI < threshold → long."""
    return SignalEngine(
        conditions=[
            SignalCondition("rsi", {"period": rsi_period}, operator="lt", value=rsi_threshold, side="long"),
        ],
        logic="any",
    )


def rsi_overbought_signal(
    rsi_period: int = 14, rsi_threshold: float = 70
) -> SignalEngine:
    """Overbought reversal: RSI > threshold → short."""
    return SignalEngine(
        conditions=[
            SignalCondition("rsi", {"period": rsi_period}, operator="gt", value=rsi_threshold, side="short"),
        ],
        logic="any",
    )


def _ema_diff(close: pd.Series, fast: int, slow: int) -> pd.Series:
    """Return EMA(fast) - EMA(slow) — positive when fast > slow (uptrend)."""
    return _compute_ema(close, fast) - _compute_ema(close, slow)


# Register derived indicator for EMA crossover
INDICATOR_COMPUTERS["ema_diff"] = lambda df, p: _ema_diff(
    df["close"], p.get("fast", 12), p.get("slow", 26)
)


def trend_follow_signal(
    ema_fast: int = 12, ema_slow: int = 26, adx_period: int = 14, adx_threshold: float = 25
) -> SignalEngine:
    """Trend follow: EMA fast > slow AND ADX > threshold (long);
    EMA fast < slow AND ADX > threshold (short).

    Uses a registered ``ema_diff`` indicator (fast - slow) for crossover
    detection, combined with ADX for trend-strength confirmation.
    Both conditions must fire on the same side (logic="all").
    """
    return SignalEngine(
        conditions=[
            # Long: EMA fast > EMA slow  (diff > 0)
            SignalCondition("ema_diff", {"fast": ema_fast, "slow": ema_slow}, operator="gt", value=0, side="long"),
            # Long: ADX > threshold (confirms trending regime)
            SignalCondition("adx", {"period": adx_period}, operator="gt", value=adx_threshold, side="long"),
            # Short: EMA fast < EMA slow  (diff < 0)
            SignalCondition("ema_diff", {"fast": ema_fast, "slow": ema_slow}, operator="lt", value=0, side="short"),
            # Short: ADX > threshold
            SignalCondition("adx", {"period": adx_period}, operator="gt", value=adx_threshold, side="short"),
        ],
        logic="all",
    )
