"""Breakout Hunter strategy.

Detects price breakouts above resistance and below support, with volume confirmation,
leveraging patterns from vibe-trading research. Captures both long and short opportunities.

Inspired by breakthrough trading techniques and verified patterns in vibe-trading.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from bot.domain.exceptions import InsufficientDataError
from bot.domain.models import Candle, Signal, SignalAction, Symbol, Timeframe

__all__ = ["BreakoutHunterStrategy"]


class BreakoutHunterStrategy:
    """Breakout Hunter strategy.

    Detects price breakouts above resistance and below support levels, with volume confirmation.
    Uses ATR-based volatility filtering and candle range validation.

    Typical configuration:
      - ``min_price_volume``: Minimum volume expansion (e.g., 1.2) to confirm breakout
      - ``atr_period``: ATR period for dynamic level calculation (e.g., 14)
      - ``volatility_filter``: ATR-based stop level filter (e.g., 0.5)
      - ``min_breakout_strength``: Minimum candlestick range for valid breakout (e.g., 0.002)
    """

    STRATEGY_ID = "breakout_hunter"
    STRATEGY_NAME = "Breakout Hunter (Price+Volume+ATR)"

    def __init__(
        self,
        min_price_volume: float = 1.2,
        atr_period: int = 14,
        volatility_filter: float = 0.5,
        min_breakout_strength: float = 0.002,
    ) -> None:
        if min_price_volume < 1.0:
            raise ValueError("min_price_volume must be >= 1.0")
        if atr_period < 1:
            raise ValueError("atr_period must be >= 1")
        if volatility_filter <= 0:
            raise ValueError("volatility_filter must be > 0")
        if min_breakout_strength <= 0:
            raise ValueError("min_breakout_strength must be > 0")
        self._min_price_volume = min_price_volume
        self._atr_period = atr_period
        self._volatility_filter = volatility_filter
        self._min_breakout_strength = min_breakout_strength

    @property
    def id(self) -> str:
        return self.STRATEGY_ID

    @property
    def name(self) -> str:
        return self.STRATEGY_NAME

    @property
    def params(self) -> dict[str, Any]:
        return {
            "min_price_volume": self._min_price_volume,
            "atr_period": self._atr_period,
            "volatility_filter": self._volatility_filter,
            "min_breakout_strength": self._min_breakout_strength,
        }

    @property
    def min_history(self) -> int:
        return max(self._atr_period + 2, 50)

    def evaluate(self, candles: Sequence[Candle]) -> Signal:
        if len(candles) < self.min_history:
            raise InsufficientDataError(
                f"{self.STRATEGY_ID} needs at least {self.min_history} bars, got {len(candles)}"
            )

        if len(candles) < 2:
            return self._create_signal(
                candles[-1],
                SignalAction.HOLD,
                0.0,
            )

        # Lookback window excludes the current candle (last one)
        lookback = self._atr_period + 1
        recent = candles[-lookback - 1 : -1]  # candles before the current one
        last_candle = candles[-1]

        prices = [float(c.close) for c in recent]
        volumes = [float(c.volume) for c in recent]

        atr = self._calculate_atr(recent)

        previous_high = max(float(c.high) for c in recent)
        previous_low = min(float(c.low) for c in recent)

        avg_volume = sum(volumes) / len(volumes) if volumes else 0.0

        current_close = float(last_candle.close)
        current_volume = float(last_candle.volume)
        candle_range = (float(last_candle.high) - float(last_candle.low)) / float(last_candle.low)

        if candle_range < self._min_breakout_strength:
            return self._create_signal(
                last_candle,
                SignalAction.HOLD,
                0.0,
            )

        if current_close > previous_high:
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
            atr_breakout = (current_close - previous_high) / atr if atr > 0 else 0
            if volume_ratio >= self._min_price_volume and atr_breakout >= self._volatility_filter:
                confidence = min(volume_ratio / 2.0, 1.0)
                return self._create_signal(
                    last_candle,
                    SignalAction.ENTER_LONG,
                    confidence,
                )

        if current_close < previous_low:
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
            atr_breakout = (previous_low - current_close) / atr if atr > 0 else 0
            if volume_ratio >= self._min_price_volume and atr_breakout >= self._volatility_filter:
                confidence = min(volume_ratio / 2.0, 1.0)
                return self._create_signal(
                    last_candle,
                    SignalAction.ENTER_SHORT,
                    confidence,
                )

        return self._create_signal(
            last_candle,
            SignalAction.HOLD,
            0.0,
        )

    def _create_signal(
        self,
        candle: Candle,
        action: SignalAction,
        confidence: float,
    ) -> Signal:
        """Helper to create a Signal with proper decision key."""
        return Signal(
            symbol=candle.symbol,
            timeframe=candle.timeframe,
            strategy_id=self.STRATEGY_ID,
            action=action,
            confidence=confidence,
            candle_timestamp=candle.datetime,
            decision_key=self._decision_key(
                candle.symbol,
                candle.timeframe,
                candle.datetime,
            ),
            params=self.params,
        )

    def _calculate_atr(self, candles: Sequence[Candle]) -> float:
        if len(candles) < 2:
            return 0.0

        tr_values = []
        for i in range(1, len(candles)):
            high = float(candles[i].high)
            low = float(candles[i].low)
            close_prev = float(candles[i - 1].close)

            tr = max(high - low, abs(high - close_prev), abs(low - close_prev))
            tr_values.append(tr)

        if not tr_values:
            return 0.0

        return sum(tr_values[-self._atr_period :]) / min(len(tr_values), self._atr_period)

    def _decision_key(
        self, symbol: Symbol, timeframe: Timeframe, candle_ts: datetime
    ) -> str:
        raw = f"{self.STRATEGY_ID}|{symbol}|{timeframe.value}|{candle_ts.isoformat()}"
        return hashlib.sha256(raw.encode()).hexdigest()