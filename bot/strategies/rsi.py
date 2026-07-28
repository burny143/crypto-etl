"""RSI Mean Reversion strategy.

Matches the calculation semantics from ``strategy_research.py``:
- RSI uses SMA of gains/losses (not Wilder's smoothed EMA).
- Signals are generated when RSI crosses below oversold (long) or
  above overbought (short).
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any

from bot.domain.exceptions import InsufficientDataError
from bot.domain.models import Candle, Signal, SignalAction, Symbol, Timeframe

__all__ = ["RsiReversionStrategy"]


class RsiReversionStrategy:
    """RSI Mean Reversion strategy.

    Default parameters (matching ``RSI_GRID`` mid-points):
      - ``period``: 14
      - ``oversold``: 30
      - ``overbought``: 70
    """

    STRATEGY_ID = "rsi_reversion"
    STRATEGY_NAME = "RSI Mean Reversion"

    def __init__(
        self,
        period: int = 14,
        oversold: int = 30,
        overbought: int = 70,
    ) -> None:
        if period < 2:
            raise ValueError("period must be >= 2")
        if not (0 < oversold < overbought < 100):
            raise ValueError(
                "expected 0 < oversold < overbought < 100, "
                f"got oversold={oversold}, overbought={overbought}"
            )
        self._period = period
        self._oversold = oversold
        self._overbought = overbought

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def id(self) -> str:
        return self.STRATEGY_ID

    @property
    def name(self) -> str:
        return self.STRATEGY_NAME

    @property
    def params(self) -> dict[str, Any]:
        return {
            "period": self._period,
            "oversold": self._oversold,
            "overbought": self._overbought,
        }

    @property
    def min_history(self) -> int:
        return self._period + 1  # need at least period+1 closes for one RSI value

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate(self, candles: Sequence[Candle]) -> Signal:
        if len(candles) < self.min_history:
            raise InsufficientDataError(
                f"{self.STRATEGY_ID} needs at least {self.min_history} bars, " f"got {len(candles)}"
            )

        closes = [float(c.close) for c in candles]
        rsi_value = _rsi(closes, self._period)

        last_candle = candles[-1]
        action, confidence = self._classify(rsi_value)

        decision_key = _decision_key(
            self.STRATEGY_ID,
            last_candle.symbol,
            last_candle.timeframe,
            last_candle.datetime,
        )

        return Signal(
            symbol=last_candle.symbol,
            timeframe=last_candle.timeframe,
            strategy_id=self.STRATEGY_ID,
            action=action,
            confidence=confidence,
            candle_timestamp=last_candle.datetime,
            decision_key=decision_key,
            params=self.params,
        )

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def _classify(self, rsi: float | None) -> tuple[SignalAction, float]:
        if rsi is None:
            return SignalAction.HOLD, 0.0

        if rsi < self._oversold:
            distance = (self._oversold - rsi) / self._oversold
            return SignalAction.ENTER_LONG, min(distance, 1.0)
        elif rsi > self._overbought:
            distance = (rsi - self._overbought) / (100.0 - self._overbought)
            return SignalAction.ENTER_SHORT, min(distance, 1.0)
        else:
            return SignalAction.HOLD, 0.0


# ====================================================================
# Pure-Python RSI (SMA-based, matching strategy_research.py)
# ====================================================================


def _rsi(closes: list[float], period: int) -> float | None:
    """Compute RSI using SMA of gains/losses (not Wilder's smoothing).

    Args:
        closes: Sequence of close prices, oldest first.
        period: RSI look-back window.

    Returns:
        RSI value (0-100) or ``None`` if insufficient data.
    """
    if len(closes) < period + 1:
        return None

    # Take the last `period + 1` closes to produce `period` deltas
    recent = closes[-(period + 1) :]
    deltas = [recent[i] - recent[i - 1] for i in range(1, len(recent))]

    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]

    # SMA of gains/losses
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_gain == 0 and avg_loss == 0:
        return 50.0  # flat market
    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


# ====================================================================
# Deterministic decision key
# ====================================================================


def _decision_key(strategy_id: str, symbol: Symbol, timeframe: Timeframe, candle_ts: object) -> str:
    """Generate a deterministic, collision-resistant key for idempotency."""
    raw = f"{strategy_id}|{symbol}|{timeframe.value}|{candle_ts}"
    return hashlib.sha256(raw.encode()).hexdigest()
